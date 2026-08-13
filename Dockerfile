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
# agent/tools/coverage.py reads this at request time to resolve character
# aliases (Gemini names the same person differently per clip) — without it
# in the image, get_coverage fails with FileNotFoundError on every call,
# which @reports_index_errors then mislabels as "the footage index is
# unreachable" (a ClickHouse-shaped error for a completely unrelated cause).
COPY data/manifest.json ./data/manifest.json

RUN pip install --no-cache-dir .[ui]

COPY --from=frontend /app/ui/dist ./ui/dist

ENV PORT=8080
CMD ["sh", "-c", "uvicorn ui.server.main:app --host 0.0.0.0 --port ${PORT}"]
