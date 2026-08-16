# Pinned Playwright image: the browser bundle and its system fonts ship with it,
# which matters twice over - no CDN fetch at build time on a mirrored registry,
# and identical font rendering, so visual baselines produced here verify here.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    FORKABLE_OFFLINE=1 \
    DO_NOT_TRACK=1 \
    # Reach a host-side Ollama; harmless when nothing is listening, because the
    # agent falls back to the deterministic engine.
    OLLAMA_HOST=http://host.docker.internal:11434

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -e ".[dev,visual]" || pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m forkable_ai_agent index

EXPOSE 8799

# Default: prove the install works. Override to run the demo or a spec.
CMD ["python", "-m", "pytest", "-q"]
