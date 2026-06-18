FROM python:3.12-slim

WORKDIR /app
COPY agentcart.py /app/agentcart.py
COPY agent.html /app/agent.html
COPY architecture.html /app/architecture.html
COPY config /app/config
COPY scripts /app/scripts

RUN useradd --system --create-home --home-dir /home/agentcart agentcart \
  && mkdir -p /data \
  && chown -R agentcart:agentcart /data /app

USER agentcart
EXPOSE 8099

CMD ["python", "/app/agentcart.py"]
