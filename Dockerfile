# EduTube (rebuilt) — static site in nginx
FROM nginx:1.27-alpine

# The catalogue is baked in at build time: 825 records, 552 KB.
COPY site/ /usr/share/nginx/html/
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

# the workspace files can be 0600; nginx workers run as an unprivileged user
RUN chmod -R a+rX /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
