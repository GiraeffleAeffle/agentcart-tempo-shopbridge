FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin household

WORKDIR /app
COPY household_os.py /app/household_os.py

RUN mkdir -p /data && chown -R household:household /data /app

USER household
EXPOSE 8088

CMD ["python", "/app/household_os.py", "serve"]
