FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Nginx site config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static files
COPY . /usr/share/nginx/html

# Config template for runtime env injection
COPY js/config.template.js /etc/nginx/templates/config.template.js

# Entrypoint: run envsubst then hand off to nginx
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
