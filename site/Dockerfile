FROM python:3.12-alpine@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4 AS build
WORKDIR /site
COPY build.py check.py release.json ./
COPY src ./src
RUN python3 build.py --out /out && python3 check.py /out

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:e2a8fca8aa356d66159aaf8a877a9c126773635adf210503eefaaeaffeed6ad7
USER root
RUN apk add --no-cache brotli-libs=1.2.1-r0
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx/ /etc/nginx/agentcart-site/
COPY --from=build /out/ /srv/agentcart-site/
USER 101
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
