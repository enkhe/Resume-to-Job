# Configuration

All configuration is via environment variables. Copy [.env.example](../../.env.example) to `.env`
for local overrides (loaded by `docker compose`; for bare `streamlit run`, export them or set in
the UI where applicable).

## Application
| Variable | Purpose | Default |
|----------|---------|---------|
| `APP_VERSION` | Shown on the Home page (Docker build arg) | `dev` |
| `DATABASE_URL` | Shared PostgreSQL database used by local + cloud runs | Azure DSN |
| `JOB_DB_PATH` | SQLite database file | `data/jobs.db` |
| `LOG_LEVEL` | Structured log level | `INFO` |

## Job ingestion
| Variable | Purpose | Default |
|----------|---------|---------|
| `JSEARCH_API_KEY` / `RAPIDAPI_KEY` | RapidAPI key for `jsearch.p.rapidapi.com` | — |
| `JOB_API_KEY` | Key for the generic job API source (e.g. Arbeitnow) | — |
| `API_JOB_LIMIT` | Default API fetch limit in the UI | `500` |

## AI recommendations (LLM)
| Variable | Purpose | Default |
|----------|---------|---------|
| `AI_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` | LLM API key (first non-empty wins) | — |
| `AI_API_BASE` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `AI_MODEL` | Model name | `gpt-4o-mini` |

For Google Gemini: `AI_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai`,
`AI_MODEL=gemini-2.5-flash`.

## CI/CD (GitHub Actions)
Configured as repository **Variables** and **Secrets** — see [CI/CD](ci-cd.md).

## Security note
Never commit real keys. `.env` is git-ignored; `.env.example` should contain placeholders only.
If a key is ever committed, **rotate it** (RapidAPI dashboard / Google AI Studio) and scrub it.
