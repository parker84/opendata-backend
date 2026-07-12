"""opendata CLI — init · ask · doctor · status · connect.

The whole first run is one command (`opendata init`): detect → confirm → index
→ prove, ending on a runnable `opendata ask` seeded from the user's own data.
See docs/onboarding.md.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable

from .config import load_config, write_config
from .connectors import REGISTRY
from .connectors.base import Env
from .context.store import ContextStore
from .engine import ask as engine_ask
from .golden.store import load_goldens, save_golden
from .golden.verify import verify_all

app = typer.Typer(add_completion=False, help="opendata — one context for your data team.")
console = Console()

# Map a connector's kind → the config key we file its connection under.
_KIND_KEY = {"warehouse": "warehouse", "semantic": "dbt"}


def _detect_all(root: Path) -> list:
    env = Env(root=root, environ=dict(os.environ))
    out = []
    for c in REGISTRY:
        try:
            r = c.detect(env)
        except Exception:  # noqa: BLE001 — one bad connector shouldn't break init
            r = None
        if r:
            out.append((c, r))
    return out


@app.command()
def init(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Project directory."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirm prompt."),
):
    """Detect existing sources, index them, and prove it with a sample answer."""
    root = path.resolve()
    console.print(f"[dim]⠿ scanning {root} and ~/.dbt …[/dim]")

    detected = _detect_all(root)
    if not detected:
        console.print("[yellow]No sources detected.[/] Try running inside a dbt project.")
        raise typer.Exit(1)

    for _c, r in detected:
        mark = "[green]✓[/]" if r.ok else "[yellow]⚠[/]"
        console.print(f"  {mark} {r.key:<12} {r.summary}")

    ready = [(c, r) for c, r in detected if r.ok]
    if not ready:
        console.print("\n[yellow]Nothing ready to connect yet — fix the ⚠ above.[/]")
        raise typer.Exit(1)

    if not yes:
        names = " + ".join(r.key for _c, r in ready)
        if not typer.confirm(f"\nConnect {names}?", default=True):
            raise typer.Abort()

    store = ContextStore.load(root)
    connections: dict[str, dict] = {}
    for c, r in ready:
        cfg = {**r.config, "_root": str(root)}
        try:
            stats = c.index(cfg, store)
        except Exception as e:  # noqa: BLE001 — a bad connector shouldn't abort init
            console.print(f"[yellow]⚠ skipped {r.key}: {e}[/]")
            continue
        connections[_KIND_KEY.get(c.kind, c.key)] = {
            k: v for k, v in r.config.items() if not k.startswith("_")
        }
        summary = " · ".join(f"{v} {k}" for k, v in stats.items())
        console.print(f"[dim]⠿ indexed {r.key}: {summary}[/dim]")

    from .context.embeddings import get_embedder

    embedder = get_embedder()
    if embedder:
        try:
            n = store.embed_catalog(embedder)
            console.print(f"[dim]⠿ embedded {n} objects ({embedder.name})[/dim]")
        except Exception as e:  # noqa: BLE001 — embeddings are best-effort
            console.print(f"[yellow]⚠ embeddings skipped: {e}[/]")

    store.save()
    write_config(
        root,
        {"version": 1, "project": root.name, "connections": connections},
    )
    console.print(f"[green]✓[/] wrote {root/'.opendata'/'config.yml'}  [dim](commit to share)[/dim]")

    goldens = load_goldens(root)
    sample = goldens[0].question if goldens else "how many rows are in each table"
    console.print(
        Panel.fit(
            f"context ready — {len(store.tables)} tables, {len(store.metrics)} metrics, "
            f"{len(goldens)} goldens.\n\n[bold]Try it:[/]\n"
            f'  [cyan]opendata ask "{sample}"[/]',
            title="[green]✓ opendata[/]",
            border_style="green",
        )
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="A question in plain language."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
):
    """Answer a question grounded in your connected context."""
    ans = engine_ask(path, question)
    if json_out:
        import json

        console.print_json(json.dumps(ans.to_dict()))
        raise typer.Exit(0 if ans.error is None else 1)
    if ans.error:
        console.print(f"[red]✗[/] {ans.error}")
        if ans.sql:
            console.print(f"[dim]{ans.sql}[/dim]")
        raise typer.Exit(1)

    prov_color = {"golden": "green", "metric": "cyan"}.get(ans.provenance.split(":")[0], "yellow")
    console.print(f"[{prov_color}]→ {ans.provenance}[/]  [dim]· {len(ans.rows)} rows[/dim]")

    table = RichTable(show_header=True, header_style="bold")
    for col in ans.columns:
        table.add_column(col)
    for row in ans.rows[:20]:
        table.add_row(*[str(v) for v in row])
    console.print(table)
    console.print(Panel(ans.sql, title="sql", border_style="dim", expand=False))


@app.command()
def save(
    question: str = typer.Argument(..., help="The question this golden answers."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
    id: str = typer.Option(None, "--id", help="Golden id (defaults to a slug)."),
    owner: str = typer.Option("", "--owner", help="Who owns this golden."),
):
    """Verify an answer and save it as a golden — reused verbatim next time."""
    ans = engine_ask(path, question)
    if ans.error:
        console.print(f"[red]✗[/] won't save — {ans.error}")
        raise typer.Exit(1)
    expects = {"columns": ans.columns, "min_rows": 1}
    p = save_golden(
        Path(path).resolve(), question, ans.sql, id=id, owner=owner, expects=expects
    )
    note = " [dim](was already golden)[/]" if ans.provenance.startswith("golden") else ""
    console.print(f"[green]✓[/] saved golden → {p}{note}  [dim](commit it)[/]")
    console.print(Panel(ans.sql, title="sql", border_style="dim", expand=False))


@app.command()
def verify(path: Path = typer.Option(Path("."), "--path", "-p")):
    """Re-run every golden; fail if any is broken or off-shape (CI-ready)."""
    results = verify_all(path)
    if not results:
        console.print("[yellow]No goldens to verify.[/]")
        raise typer.Exit(0)
    failed = 0
    for r in results:
        mark = "[green]✓[/]" if r.ok else "[red]✗[/]"
        console.print(f"  {mark} {r.golden.id:<28} [dim]{r.detail}[/]")
        failed += 0 if r.ok else 1
    console.print(f"\n{len(results) - failed}/{len(results)} goldens verified")
    raise typer.Exit(1 if failed else 0)


@app.command()
def status(path: Path = typer.Option(Path("."), "--path", "-p")):
    """Show what's connected and how much context opendata has."""
    root = path.resolve()
    cfg = load_config(root)
    if not cfg:
        console.print("[yellow]Not initialized here.[/] Run [cyan]opendata init[/].")
        raise typer.Exit(1)
    store = ContextStore.load(root)
    goldens = load_goldens(root)
    console.print(f"[bold]{cfg.get('project', root.name)}[/]")
    for key, conn in (cfg.get("connections") or {}).items():
        console.print(f"  [green]✓[/] {key:<10} {conn.get('type', conn.get('manifest', ''))}")
    console.print(
        f"\n  tables: {len(store.tables)}   metrics: {len(store.metrics)}   "
        f"goldens: {len(goldens)}"
    )


@app.command()
def doctor(path: Path = typer.Option(Path("."), "--path", "-p")):
    """Diagnose the setup; every failure names its one-command fix."""
    root = path.resolve()
    cfg = load_config(root) or {}
    conns = cfg.get("connections", {}) or {}
    any_fail = False
    for c in REGISTRY:
        key = _KIND_KEY.get(c.kind, c.key)
        conn = conns.get(key)
        if conn is None:
            continue
        for chk in c.validate({**conn, "_root": str(root)}):
            mark = "[green]✓[/]" if chk.ok else "[red]✗[/]"
            console.print(f"  {mark} {chk.name:<18} {chk.detail}")
            if not chk.ok and chk.fix:
                console.print(f"      [dim]→ fix:[/] [cyan]{chk.fix}[/]")
                any_fail = True
    if not conns:
        console.print("[yellow]Nothing connected.[/] Run [cyan]opendata init[/].")
    raise typer.Exit(1 if any_fail else 0)


@app.command()
def eval(path: Path = typer.Option(Path("."), "--path", "-p")):
    """Score the answer engine against the golden set (architecture §7)."""
    from .eval.harness import run as run_eval

    report = run_eval(path)
    if not report.cases:
        console.print("[yellow]No goldens to evaluate.[/] Add some in .opendata/golden/.")
        raise typer.Exit(0)
    for c in report.cases:
        mark = "[green]✓[/]" if c.ok else "[red]✗[/]"
        console.print(f"  {mark} {c.question:<45} [dim]{c.detail}[/]")
    pct = round(report.accuracy * 100)
    color = "green" if report.accuracy == 1 else "yellow" if report.accuracy >= 0.5 else "red"
    console.print(f"\n[{color}]accuracy: {pct}%[/]  ({sum(c.ok for c in report.cases)}/{len(report.cases)})")
    raise typer.Exit(0 if report.accuracy == 1 else 1)


@app.command()
def serve(
    path: Path = typer.Option(Path("."), "--path", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
):
    """Serve the read-only HTTP API (needs the [server] extra)."""
    try:
        from .api.server import serve as _serve
    except ImportError:
        console.print("[red]Install the server extra:[/] pip install 'opendata[server]'")
        raise typer.Exit(1)
    console.print(f"[green]opendata[/] serving {Path(path).resolve()} at http://{host}:{port}")
    _serve(Path(path).resolve(), host=host, port=port)


@app.command()
def connect(source: str = typer.Argument(..., help="e.g. posthog, looker")):
    """Add another source (stub — catalog grows here)."""
    console.print(f"[yellow]connector '{source}' not implemented yet[/] — see docs/onboarding.md §5")


if __name__ == "__main__":
    app()
