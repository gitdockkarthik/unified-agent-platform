// ── Runtime config ─────────────────────────────────────────────────────────────
// Injected by docker-entrypoint.sh from env vars; falls back to localhost for dev.
const BACKEND_URL = (window.__CONFIG__?.BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');
const API_KEY     = window.__CONFIG__?.API_KEY || '';

// ── Agent accent colours ────────────────────────────────────────────────────────
const ACCENT_CLASSES = ['ca-0','ca-1','ca-2','ca-3','ca-4','ca-5','ca-6','ca-7'];

function agentAccentClass(slug) {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (Math.imul(31, h) + slug.charCodeAt(i)) | 0;
  return ACCENT_CLASSES[Math.abs(h) % ACCENT_CLASSES.length];
}

// ── Session management ──────────────────────────────────────────────────────────
function generateSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function getOrCreateSession(agentSlug) {
  const key = `session_${agentSlug}`;
  let sid = sessionStorage.getItem(key);
  if (!sid) { sid = generateSessionId(); sessionStorage.setItem(key, sid); }
  return sid;
}

function resetSession(agentSlug) {
  const key = `session_${agentSlug}`;
  const sid = generateSessionId();
  sessionStorage.setItem(key, sid);
  return sid;
}

// ── HTTP helpers ────────────────────────────────────────────────────────────────
async function _json(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function _authHeaders() {
  return API_KEY ? { 'X-API-Key': API_KEY } : {};
}

// ── Public API ──────────────────────────────────────────────────────────────────

/** Fetch published agents (no auth required). */
async function fetchAgents() {
  return _json(await fetch(`${BACKEND_URL}/api/agents`));
}

/** Fetch all agents including drafts (requires X-API-Key). */
async function fetchAllAgents({ status } = {}) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return _json(await fetch(`${BACKEND_URL}/api/registry/agents${qs}`, {
    headers: _authHeaders(),
  }));
}

/** Get a single published agent by slug. */
async function fetchAgent(slug) {
  return _json(await fetch(`${BACKEND_URL}/api/agents/${encodeURIComponent(slug)}`));
}

/** Register a new agent manifest. */
async function registerAgent(data) {
  return _json(await fetch(`${BACKEND_URL}/api/registry/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify(data),
  }));
}

/** Publish an agent by registry ID. */
async function publishAgent(agentId) {
  return _json(await fetch(`${BACKEND_URL}/api/registry/agents/${agentId}/publish`, {
    method: 'POST',
    headers: _authHeaders(),
  }));
}

/** Deprecate an agent by registry ID. */
async function deprecateAgent(agentId) {
  return _json(await fetch(`${BACKEND_URL}/api/registry/agents/${agentId}/deprecate`, {
    method: 'POST',
    headers: _authHeaders(),
  }));
}

/** Fetch chat history for a session UUID. */
async function getHistory(sessionId) {
  return _json(await fetch(`${BACKEND_URL}/api/session/${encodeURIComponent(sessionId)}`));
}

/**
 * Invoke an agent with streaming display.
 *
 * Reads the response body via ReadableStream. The current backend returns
 * full JSON (ready for SSE when a /stream endpoint is added). Displays the
 * assistant text character-by-character via requestAnimationFrame.
 *
 * @param {string}   slug       — agent slug
 * @param {string}   message    — user message
 * @param {string}   sessionId  — UUID string
 * @param {Object}   context    — optional per-agent context (report data, etc.)
 * @param {Function} onChunk    — called with each character as it renders
 * @param {Function} onDone     — called with the full response object when complete
 * @param {Function} onError    — called with an Error on failure
 */
async function invokeAgent(slug, message, sessionId, context, onChunk, onDone, onError) {
  let res;
  try {
    res = await fetch(`${BACKEND_URL}/api/invoke/${encodeURIComponent(slug)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._authHeaders() },
      body: JSON.stringify({
        session_id: sessionId,
        user_message: message,
        context: context || {},
        history: [],   // backend loads history from DB by session_id
      }),
    });
  } catch (err) {
    onError(err);
    return;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    onError(new Error(body.detail || `HTTP ${res.status}`));
    return;
  }

  // Consume via ReadableStream — positions code for SSE upgrade later
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let raw = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      raw += decoder.decode(value, { stream: true });
    }
    raw += decoder.decode();
  } catch (err) {
    onError(err);
    return;
  }

  let data;
  try { data = JSON.parse(raw); }
  catch (err) { onError(new Error('Invalid response from server')); return; }

  // Stream the text to the UI character-by-character
  const text = data.response || '';
  let i = 0;
  const CHARS_PER_FRAME = 4;
  function tick() {
    for (let c = 0; c < CHARS_PER_FRAME && i < text.length; c++) onChunk(text[i++]);
    if (i < text.length) requestAnimationFrame(tick);
    else onDone(data);
  }
  requestAnimationFrame(tick);
}

// ── Markdown renderer ───────────────────────────────────────────────────────────
// Handles the most common Claude output patterns without an external library.
function renderMarkdown(raw) {
  let s = raw
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Fenced code blocks
  s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`);
  // Inline code
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold / italic
  s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  // Headers
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm,   '<h1>$1</h1>');
  // Unordered lists
  s = s.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`);
  // Ordered lists
  s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Horizontal rule
  s = s.replace(/^---+$/gm, '<hr>');
  // Paragraphs (double newlines outside blocks)
  s = s.replace(/\n{2,}/g, '</p><p>');
  s = s.replace(/\n/g, '<br>');
  return `<p>${s}</p>`;
}

// ── Toast notifications ─────────────────────────────────────────────────────────
let _toastContainer;
function _ensureToasts() {
  if (!_toastContainer) {
    _toastContainer = document.createElement('div');
    _toastContainer.className = 'toast-container';
    document.body.appendChild(_toastContainer);
  }
}

function showToast(message, type = 'success') {
  _ensureToasts();
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.innerHTML = `<span class="toast__dot"></span>
    <span class="toast__text">${message}</span>
    <button class="toast__close" aria-label="Dismiss">×</button>`;
  el.querySelector('.toast__close').onclick = () => el.remove();
  _toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

// ── Misc helpers ────────────────────────────────────────────────────────────────
function formatTime(isoString) {
  if (!isoString) return '';
  try {
    return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(isoString));
  } catch { return ''; }
}

function truncate(str, n) {
  return str && str.length > n ? str.slice(0, n) + '…' : str;
}
