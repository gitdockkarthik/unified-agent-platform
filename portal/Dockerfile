FROM nginx:alpine

# Remove default nginx config — our entrypoint writes the final conf at runtime
RUN rm /etc/nginx/conf.d/default.conf

# Static files
COPY . /usr/share/nginx/html

# Templates processed at container start by docker-entrypoint.sh
COPY js/config.template.js /etc/nginx/templates/config.template.js
COPY nginx.conf /etc/nginx/templates/nginx.conf.template

# Entrypoint: substitutes env vars then execs nginx
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

CMD ["/docker-entrypoint.sh"]
