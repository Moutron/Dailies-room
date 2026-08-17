# Deployed with `gcloud run deploy dailies-ui --source .` from the repo
# root, NOT `--source ./ui` as 8.7's spec literally reads — the backend
# (ui/server/) imports agent/, pipeline/, and schema/ from the repo root
# (`from agent.agent import root_agent`), so the build context has to be the
# whole repo, not just ui/. Documented as a deliberate deviation in docs/UI.md.

FROM node:20-slim AS frontend
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

COPY pyproject.toml ./
COPY agent/ ./agent/
COPY pipeline/ ./pipeline/
COPY schema/ ./schema/
COPY ui/__init__.py ./ui/__init__.py
COPY ui/server/ ./ui/server/
COPY data/thumbs/ ./data/thumbs/
COPY data/posters/ ./data/posters/
# agent/tools/coverage.py reads this at request time to resolve character
# aliases (Gemini names the same person differently per clip) — without it
# in the image, get_coverage fails with FileNotFoundError on every call,
# which @reports_index_errors then mislabels as "the footage index is
# unreachable" (a ClickHouse-shaped error for a completely unrelated cause).
COPY data/manifest.json ./data/manifest.json

# pipeline/encode.py (frame-sequence uploads) and pipeline/posters.py
# (poster extraction) both shell out to ffmpeg at request time, not just in
# the offline pipeline scripts -- ui/server/upload.py calls them
# synchronously inside POST /ingest/upload, so ffmpeg has to exist in the
# runtime image itself, not just wherever the offline scripts happen to run.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir .[ui]

COPY --from=frontend /app/ui/dist ./ui/dist

ENV PORT=8080
CMD ["sh", "-c", "uvicorn ui.server.main:app --host 0.0.0.0 --port ${PORT}"]
