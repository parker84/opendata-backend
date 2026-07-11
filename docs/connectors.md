# Connectors — the community ecosystem

> The long tail of connectors is built by the community. That's the point of
> being open source — and it's opendata's compounding moat.

Every data stack is different. No single company can build and maintain a
connector for every warehouse, BI tool, catalog, and SaaS source. An open,
easy-to-extend connector system lets the community cover the long tail while the
core team maintains the top ~10 — and every new connector makes opendata more
valuable to everyone. A closed competitor can't match that surface area.

Precedent for this working: **dbt adapters**, **Airbyte/Singer taps**,
**Terraform providers**, **Grafana plugins** — all ecosystems where the community
vastly outbuilds the core team.

---

## 1. What a connector is

Two kinds (see `architecture.md §5` for the protocol):

- **Context connectors** (`kind`: `semantic` / `bi` / `product` / `prose`) — pull
  metadata into the context store: schema, metrics, dashboards, past analysis.
  *Most community connectors are these* (PostHog, Looker, Metabase, Notion…).
- **Warehouse adapters** (`kind`: `warehouse`) — also *execute* read-only SQL and
  own a dialect. More sensitive (security, correctness); expect a higher bar.

Every connector implements the same small contract:

```python
class Connector(Protocol):
    key: str          # "posthog"
    kind: str         # "product"
    def detect(self, env)  -> DetectResult | None   # fast, side-effect-free
    def validate(self, cfg) -> list[HealthCheck]     # read-only; powers `doctor`
    def grant_sql(self, cfg) -> str | None           # least-priv setup to paste
    def index(self, cfg, store) -> dict              # pull metadata into context
```

Keep the surface tiny — a small, stable, versioned contract is the whole reason
the barrier stays low.

---

## 2. Distribution — no core PR required

Community connectors ship as **their own PyPI package** and are **auto-discovered**
via the `opendata.connectors` entry-point group (the dbt-adapter / pytest-plugin
model). Installing one makes the source available; opendata never has to know
about it in advance.

```toml
# in opendata-connector-posthog / pyproject.toml
[project.entry-points."opendata.connectors"]
posthog = "opendata_connector_posthog:PostHogConnector"
```

```bash
pip install opendata-connector-posthog
opendata connect posthog     # it's just there
```

At startup opendata loads every entry point in that group, instantiates the
class, and registers it (`connectors/__init__.py`). One bad plugin can't break
the CLI; duplicates are deduped by `key`.

Naming convention: **`opendata-connector-<source>`** (PyPI) exposing
**`<Source>Connector`**.

---

## 3. Scaffolding — barrier ≈ zero

```bash
opendata connector new posthog     # (planned) generates a template repo
```

The template ships: the four protocol methods stubbed, a `pyproject.toml` with
the entry point wired, a fixture, and the conformance tests (below) pre-imported.
"Write a connector" should mean "fill in four methods and run the tests."

---

## 4. Conformance test kit

opendata publishes a shared contract-test suite (`opendata.testing`) that every
connector runs against a fixture:

- `detect()` is side-effect-free and returns a valid `DetectResult` (or `None`)
- `validate()` never mutates and reports actionable `HealthCheck`s
- `index()` is idempotent and populates the store with well-formed entities
- warehouse adapters: `execute()` honors the read-only guard + `LIMIT`

Passing the kit is what earns the **verified** badge (below). Same idea as
Airbyte's Connector Acceptance Tests or dbt's adapter test suite — consistent
quality without hand-review of every line.

---

## 5. Trust tiers & security

Connectors run **in the user's environment, with real credentials** — so trust is
explicit, not implied.

| Tier | Meaning |
|---|---|
| **official** | built + maintained by core |
| **verified** | passes the conformance kit + a security review; declared scopes |
| **community** | published, unreviewed — installs with a clear "community" notice |

Security posture, non-negotiable:

- **Read-only by default.** Warehouse adapters route all SQL through the parse-
  time guard; a connector that needs writes is rejected.
- **Least privilege.** `grant_sql()` generates the minimal role to paste; connectors
  declare the scopes/capabilities they use.
- **Creds stay local.** Secrets come from env/keychain by reference; connectors
  must never log or exfiltrate them. Indexing is auditable (what was read).
- **Provenance.** Verified connectors are reviewed; signing/attestation is on the
  roadmap for the registry.

---

## 6. The registry / hub

A discoverable catalog (`connectors.json` → a hub page) listing each connector's
install command, maintainer, tier badge, supported entities, and popularity — the
dbt Hub / Terraform Registry equivalent. This is where a data team goes to ask
"is my tool supported?" and where contributors get visible credit.

---

## 7. Contributing

- **Good first connectors** (high demand, low complexity): Metabase, DuckDB
  files, Postgres, CSV/Parquet folders, Notion.
- Start from `opendata connector new`, make the conformance kit green, publish to
  PyPI, open a registry PR.
- `CONTRIBUTING.md` (roadmap) covers the full flow; the protocol is the contract —
  we keep it stable and version it.

---

## 8. Why this is strategy, not just plumbing

- **Network effect** — each connector raises the value of the whole workspace;
  coverage compounds without core headcount.
- **Moat** — long-tail breadth is exactly what a closed BI/ELT vendor can't
  replicate on adoption alone.
- **Monetization stays aligned** — connectors are free and open (the adoption
  engine). What's paid is the *managed running* of them (always-on sync, managed
  OAuth, the VPC connector-agent) and a **verified/partner program**. See the
  private strategy repo.
