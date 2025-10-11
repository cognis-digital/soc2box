FROM python:3.12-slim
LABEL org.opencontainers.image.title="cognis-soc2box"
LABEL org.opencontainers.image.source="https://github.com/cognis-digital/soc2box"
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
ENTRYPOINT ["soc2box"]
