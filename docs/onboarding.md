# Onboarding Design — opendata

> Seamless onboarding for data teams: connect to what you already have, in under
> two minutes, with zero forms.

This is the design spec for how a data team goes from "never heard of opendata"
to "asking questions grounded in our own warehouse, metrics, and past analysis."
Onboarding is the single most important surface for an adoption-led,
open-source tool — the moat is usage, and the only thing between a data team and
usage is **auth friction**. This document is about removing it.

---

## 1. North-star metric

**Time-to-first-grounded-answer (TTFGA):** how long from `opendata init` until
the user sees a real answer, computed from *their* data, with the SQL and the
lineage shown.

- **Target: < 2 minutes, zero forms.**
- Everything in this doc is justified by whether it moves TTFGA down.
- **Activation** (for measurement) = *1 source connected + 1 successful grounded
  ask*. See §11.

Non-goals for v1: a hosted control plane, SSO/SCIM, a click-through web wizard.
Those come after the CLI onboarding is magic.

---

## 2. The core insight: auto-detect, don't ask

Data teams already have their credentials and metadata on disk. The biggest
lever in the entire onboarding is **never asking them to type what already
exists.** Before we prompt for anything, we scan for it.

| We look for… | …to get | New auth needed? |
|---|---|---|
| `./` + `dbt_project.yml` | the dbt project + its `target/manifest.json` | **No — it's a file** |
| `~/.dbt/profiles.yml` | warehouse connection(s), and which target is `prod` | No — reuse |
| `DATABASE_URL`, `SNOWFLAKE_*`, `GOOGLE_APPLICATION_CREDENTIALS`, gcloud ADC | warehouse auth already configured on the machine | No — reuse |
| `.opendata/config.yml` (committed by a teammate) | the whole team setup | No — reuse |
| the git remote | team / project identity | No |

**The dbt `manifest.json` is the hero.** For any dbt shop it delivers every
model, metric, test, doc string, and lineage edge — the richest possible
context — *with no new credentials at all*, because it is already sitting in
`target/`. We lead with it: a dbt team gets meaningful context before
authorizing a single thing.

---

## 3. The `opendata init` experience

The entire first run is one command. No dashboard, no signup wall. The "aha"
(a grounded answer) is baked into the first screen.

```
$ npx opendata init          # or: opendata init  (if installed)

⠿ scanning ./ and ~/.dbt …
  ✓ dbt project      analytics   (312 models · 27 metrics)
  ✓ warehouse        snowflake · profile "prod"  (read-only role detected)
  ✓ query history    QUERY_HISTORY accessible
  ⚠ posthog          not connected  → opendata connect posthog

Connect analytics + snowflake:prod?  [Y/n] › y

⠿ indexing manifest.json … 312 models
⠿ indexing schema … 1,204 tables
⠿ indexing 6 mo query history … 8,410 queries
✓ wrote .opendata/config.yml   (commit this to share with your team)

✓ context ready in 71s.  Try it:

  $ opendata ask "weekly active teams, last 8 weeks"
  → metric active_team (metrics/activity.yml) · warehouse.events ⨝ dim_teams
  → 8 rows · grounded in dashboard #142
```

Design rules for the flow:

1. **Detect → confirm → index → prove.** In that order, always.
2. **One connection is enough to get value.** Warehouse *or* dbt alone must
   produce a real answer. Everything else is an optional "add later" nudge, never
   a gate.
3. **End on the aha, not a menu.** The last line the user sees is a runnable
   `opendata ask` seeded from their own data.
4. **Write the config for them.** Onboarding produces a versionable file (§8) so
   the second teammate's onboarding is instant.
5. **Idempotent.** Re-running `init` reconciles against existing config; it never
   duplicates or clobbers.

### Sub-commands

- `opendata init` — detect + connect the obvious sources + index + prove.
- `opendata connect <source>` — add one more source (`posthog`, `looker`, …).
- `opendata doctor` — diagnose + suggest one-command fixes (§9).
- `opendata ask "<question>"` — the payoff; grounded answer + SQL + lineage.
- `opendata status` — what's connected, last indexed, context size.

---

## 4. The connector interface

Connectors are pluggable so the catalog can grow without touching core. Each
connector implements a small, uniform contract. (Illustrative Python — the data
ecosystem is Python-native; treat as a shape, not final API.)

```python
class Connector(Protocol):
    key: str                      # "snowflake", "dbt_core", "posthog", …
    kind: Literal["warehouse", "semantic", "bi", "product", "prose"]

    def detect(self, ctx: Env) -> DetectResult | None:
        """Look in cwd + standard locations + env. Cheap, no network.
        Returns a candidate connection (never prompts, never writes)."""

    def validate(self, cfg: ConnConfig) -> HealthReport:
        """Read-only connectivity + permission check. Powers `doctor`."""

    def grant_sql(self, cfg: ConnConfig) -> str | None:
        """Least-privilege setup to copy-paste (warehouses). None if N/A."""

    def index(self, cfg: ConnConfig, sink: ContextSink) -> IndexStats:
        """Pull schema / metrics / dashboards / history into the context store.
        Incremental + resumable."""
```

`detect()` is the magic: it must be fast, side-effect-free, and it is what powers
the auto-detected checklist in §3. Adding a connector = shipping these four
methods.

---

## 5. Connector catalog

Ordered by onboarding priority. "Easy path" is what we try first; there is
always a manual fallback (paste a connection string / API key).

| Source | Easy path (auto) | Zero-effort trick | What we pull |
|---|---|---|---|
| **dbt Core** | find `dbt_project.yml` → read `target/manifest.json` | **no new auth — it's a file** | models, metrics, tests, docs, lineage |
| **Snowflake / BigQuery / Postgres / Databricks** | reuse `~/.dbt/profiles.yml` / env / ADC | detect creds; **generate read-only `GRANT`** | schema, columns, `QUERY_HISTORY` |
| **dbt Cloud** | service token / OAuth | 1 click | + run history, Semantic Layer metrics |
| **PostHog** | "Authorize" (OAuth) or personal API key | 1 click | events schema, insights, dashboards |
| **Looker** | API3 key / OAuth | reads **LookML** (a full semantic layer) | explores, looks, dashboards |
| **Metabase / Mode / Hex / Tableau** | API key / OAuth | read-only | saved questions, dashboards, notebooks |
| **Slack / Notion** (past analysis) | OAuth | 1 click | prose analyses + decisions |

**Auth taxonomy** (drives the UX):

- **Local-cred / file** (warehouses via dbt profiles, dbt Core): *auto-detected*,
  no prompt. The 80% case for the first connection.
- **API key / token** (PostHog, Looker, Metabase, Mode, Hex): one paste, or one
  env var. CLI-friendly.
- **OAuth** (dbt Cloud, PostHog cloud, Slack, Notion): one "Authorize" click —
  used by the hosted web flow (§10) and available in CLI via device-code.

---

## 6. Trust & security model

This is what actually kills data-tool signups. Onboarding must *reduce* perceived
risk at every step, not add to it.

1. **Read-only, least-privilege — and we generate the setup *for* them.** We never
   say "go make a read-only role." We print the exact SQL to copy-paste:

   ```sql
   -- opendata: least-privilege, read-only. Run in Snowflake as ACCOUNTADMIN.
   CREATE ROLE IF NOT EXISTS OPENDATA_RO;
   GRANT USAGE ON WAREHOUSE ANALYTICS_WH   TO ROLE OPENDATA_RO;
   GRANT USAGE ON DATABASE  ANALYTICS      TO ROLE OPENDATA_RO;
   GRANT USAGE ON ALL SCHEMAS IN DATABASE  ANALYTICS TO ROLE OPENDATA_RO;
   GRANT SELECT ON ALL TABLES IN DATABASE  ANALYTICS TO ROLE OPENDATA_RO;
   GRANT SELECT ON FUTURE TABLES IN DATABASE ANALYTICS TO ROLE OPENDATA_RO;
   -- optional: read query history for "past analysis" context
   GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE OPENDATA_RO;
   ```

   This removes the "I have to bug my data-platform admin" blocker — they can hand
   this snippet to whoever owns the warehouse.

2. **Local-first / self-host.** opendata is open source; in the CLI/self-hosted
   mode, **credentials and data never leave the machine or the team's infra.** Say
   this loudly. It answers the security objection before it's raised.

3. **VPC connector-agent (hosted, later).** For the eventual hosted product, do
   *not* ask customers to paste warehouse creds into a SaaS. Run a lightweight
   agent inside their VPC (the Fivetran/Hightouch/Prefect pattern) so creds stay
   put and only derived context leaves.

4. **Secrets never touch the repo.** Connection secrets live in the OS keychain or
   env vars, referenced by name from the config file (§8). The committed config
   contains *no secrets*.

5. **Scoped, auditable indexing.** Log exactly what was read (schemas, row counts).
   Support allow/deny lists for schemas and PII columns from day one.

---

## 7. Config file — `.opendata/config.yml`

Onboarding *writes this for you*, but it is human-readable, PR-able, and
team-shareable. Committing it makes the next teammate's `init` instant. **No
secrets** — only references.

```yaml
version: 1
project: analytics                 # from git remote / dbt_project.yml
connections:
  warehouse:
    type: snowflake
    profile: prod                  # resolved from ~/.dbt/profiles.yml
    role: OPENDATA_RO              # read-only role we generated
    secret_ref: env:SNOWFLAKE_PASSWORD   # reference, never the value
    include_query_history: true
  dbt:
    type: dbt_core
    project_dir: .
    manifest: target/manifest.json
  posthog:                         # added later via `opendata connect posthog`
    type: posthog
    host: https://us.posthog.com
    secret_ref: keychain:opendata/posthog
index:
  schemas_allow: ["analytics.*", "marts.*"]
  pii_deny: ["*.email", "*.ssn"]
```

---

## 8. `opendata doctor`

Onboarding breaks in predictable ways (expired token, missing grant, wrong
target). `doctor` is the self-diagnosing health check — the `dbt debug` /
`gh auth status` of opendata. Every failure names the fix.

```
$ opendata doctor

  ✓ dbt project       manifest.json fresh (2m ago)
  ✓ snowflake:prod    connected · OPENDATA_RO · 1,204 tables
  ✗ query history     permission denied on SNOWFLAKE.ACCOUNT_USAGE
      → fix:  GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE OPENDATA_RO;
  ⚠ posthog           token expires in 3 days
      → fix:  opendata connect posthog --reauth
```

Rule: a failing check is never a dead end — it always ships the one command that
resolves it.

---

## 9. Hosted / web onboarding (later)

Once the CLI flow is magic, the hosted web version mirrors it:

- **OAuth "Authorize" cards** for SaaS sources (PostHog, dbt Cloud, Looker,
  Slack, Notion) — the same connectors, different auth transport.
- **Warehouse via the VPC agent** (§6.3), not a creds form.
- The same **detect → confirm → index → prove** arc, ending on a grounded answer
  in the browser.
- The web `/connect` screen is speced separately (see `opendata-web`).

---

## 10. Activation metrics & instrumentation

Treat onboarding as an experiment surface from day one.

- **Activation** = 1 source connected **and** 1 successful grounded ask.
- **TTFGA** = timestamp(first successful ask) − timestamp(`init` start).
- **Per-connector success rate** = validated / attempted, sliced by auth type.
- **Step drop-off** = funnel across detect → confirm → index → first ask.
- **Second-seat time** = how long teammate #2 takes when config is committed
  (should approach zero — the payoff of §7).

Self-hosted telemetry must be **opt-in and anonymous** (open-source norm). Ship a
local `opendata status --funnel` so a team can see their own onboarding health
even with telemetry off.

---

## 11. Open questions

- **Language/runtime** for the connector SDK (Python-first for ecosystem fit vs.
  a single distributable binary à la opencode). Decide before the catalog grows.
- **Context store**: where indexed schema/metrics/history live (local SQLite/
  DuckDB + object storage?) and how incremental re-index is triggered.
- **Semantic-layer precedence**: when dbt metrics *and* LookML *and* a warehouse
  view disagree on a metric, which wins? (Onboarding should surface the conflict,
  not silently pick.)
- **Refresh model**: manifest/schema drift detection and re-index cadence.

---

*Design owner: @brydon. Status: draft for v1 CLI onboarding.*
