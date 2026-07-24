FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY lib/temporal/ lib/temporal/
RUN pip install --no-cache-dir uv && uv sync --no-dev --frozen

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/FlowFeel/imi-pipeline"
LABEL org.opencontainers.image.description="IMI Syndication Pipeline Worker"
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY src/ src/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "from phosphene.imi.workflow import SyndicationSagaWorkflow; print('ok')"
ENTRYPOINT ["python", "-m", "phosphene.imi.worker"]
