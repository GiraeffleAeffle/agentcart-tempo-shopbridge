FROM python:3.11-slim

WORKDIR /app
COPY agentcart.py /app/agentcart.py
COPY shopbridge-direct-skill/scripts/shopbridge_safe_http.py /app/shopbridge-direct-skill/scripts/shopbridge_safe_http.py
COPY shopbridge-direct-skill/scripts/shopbridge_registry_trust.py /app/shopbridge-direct-skill/scripts/shopbridge_registry_trust.py
COPY shopbridge-direct-skill/scripts/shopbridge_onchain_projection.py /app/shopbridge-direct-skill/scripts/shopbridge_onchain_projection.py
COPY *.html /app/
COPY config /app/config
COPY scripts /app/scripts

RUN useradd --system --create-home --home-dir /home/agentcart agentcart \
  && mkdir -p /data \
  && chown -R agentcart:agentcart /data /app

USER agentcart
EXPOSE 8099

CMD ["python", "/app/agentcart.py"]
