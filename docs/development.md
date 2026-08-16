# Development guide

## Repository layout (to be created in Phase 0)

```
.
├── apps/
│   ├── api/                  # FastAPI + Arq worker (Python 3.12, uv)
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/routes/
│   │   │   ├── core/         # config, logging
│   │   │   ├── db/           # session, models, repositories
│   │   │   ├── services/
│   │   │   └── worker.py     # Arq settings
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── alembic.ini
│   └── web/                  # Next.js 15
│       ├── app/
│       ├── components/
│       ├── lib/
│       └── package.json
├── infra/
│   ├── docker-compose.yml
│   └── postgres/init.sql     # create extension vector
├── scripts/
│   └── eval_retrieval.py
├── tests/fixtures/           # PDFs + evalset.json
├── docs/
└── README.md
```

No shared npm package in v1. Types are duplicated lightly or generated later.

## Tooling

| Concern | Tool |
| --- | --- |
| Python deps / venv | uv |
| Python lint | ruff |
| Python types | mypy (strict on `app/services`) |
| Python tests | pytest + pytest-asyncio |
| Node | Node 22, npm |
| JS lint | eslint + prettier (Next defaults) |
| DB migrations | Alembic |
| Compose | Docker Compose v2 |

## Environment

`.env.example`:

```
POSTGRES_URL=postgresql+asyncpg://lmrag:lmrag@127.0.0.1:5433/lmrag
REDIS_URL=redis://127.0.0.1:6379/0
OLLAMA_HOST=http://127.0.0.1:11434
DATA_DIR=./data
MAX_UPLOAD_BYTES=52428800
EMBED_MODEL=nomic-embed-text
VISION_MODEL=qwen2.5vl:7b
GENERATE_MODEL=qwen2.5:7b
EMBEDDING_DIM=768
```

`DATA_DIR` is gitignored.

## Local run

From the repo root, after Docker, Ollama, uv, and Node 22 are installed:

```bash
./scripts/dev.sh              # macOS / Linux
.\scripts\dev.ps1             # Windows
```

`--setup-only` stops after deps/models/migrate. `--skip-setup` just starts Postgres/Redis plus the three app processes. `--no-pull` skips Ollama downloads.

Manual equivalent:

1. `docker compose -f infra/docker-compose.yml up -d`
2. `ollama pull nomic-embed-text` (and generate/vision tags)
3. `uv sync` in `apps/api`, `alembic upgrade head`, `uvicorn` + `arq`
4. `npm run dev` in `apps/web`

## Conventions

- Functions and modules do one thing; files stay small
- No business logic in route modules — routes call services
- Services do not import FastAPI
- Repositories own SQLAlchemy queries; services do not scatter `select()` calls
- Chunker, RRF, citation parser are pure functions with tests first
- Commit messages: `feat:`, `fix:`, `docs:`, `chore:` — one logical change per commit (when the user asks to commit)

## Testing commands

```
cd apps/api && uv run pytest -q
cd apps/web && npm test
uv run python scripts/eval_retrieval.py
```

Integration tests marked `@pytest.mark.integration` require Compose. Default CI (when added) runs unit tests only.

## Definition of done for a backend task

1. Test written and failing, then implementation
2. Ruff clean
3. Migration if schema changed
4. API doc updated if HTTP changed

## Naming

- Product: Local Multimodal RAG
- Python package: `app`
- Docker project: `lmrag`
- DB name / role: `lmrag`
