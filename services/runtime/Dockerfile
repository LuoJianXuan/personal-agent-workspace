ARG DOCKER_REGISTRY=docker.io
FROM ghcr.io/astral-sh/uv:0.8.10 AS uv
FROM ${DOCKER_REGISTRY}/library/python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app app
COPY contracts contracts
COPY skills skills
RUN useradd -u 10001 -m workspace
USER workspace
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
