# opendata

The open-source data workspace in the AI era.

**10× the impact your data team can have.**

Connecting your warehouse / dashboards / metric definitions / previous analysis —
all together in the same place, with the same context. So your data team (and the
AI agents working alongside them) answer questions grounded in one source of
truth, instead of re-deriving the same number twice.

Inspired by OpenCode. Built for data teams.

## Quickstart (offline demo)

Runs end-to-end with no external database and no LLM API key, against a bundled
toy dbt + DuckDB fixture:

```bash
uv venv && uv pip install -e .

opendata init  --yes --path examples/toy
opendata ask   "weekly active teams last 8 weeks" --path examples/toy
opendata status --path examples/toy
opendata doctor --path examples/toy
```

`init` auto-detects the dbt project + warehouse, indexes schema + metrics, and
proves it with a grounded answer. `ask` resolves **golden SQL → defined metric →
generated SQL**, validates it (read-only + `LIMIT`), executes, and shows the SQL
and provenance.

## Docs

- [`docs/architecture.md`](docs/architecture.md) — how it's built.
- [`docs/onboarding.md`](docs/onboarding.md) — seamless, auto-detecting onboarding.
- [`docs/golden-sql.md`](docs/golden-sql.md) — the golden SQL curation layer.

## Status

`v0.1` — a runnable vertical slice (dbt Core + DuckDB + offline engine + CLI).
See the docs for the build order to real warehouses, a Claude provider,
embeddings retrieval, an eval harness, and the API server.
