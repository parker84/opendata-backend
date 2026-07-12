"""Golden library — verified (question → SQL/metric) pairs (see docs/golden-sql.md).

Goldens are `.sql` files with a small YAML frontmatter header, living in
`.opendata/golden/`. They're git-native, PR-reviewable, and reused verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


@dataclass
class Golden:
    id: str
    question: str
    sql: str
    aliases: list[str] = field(default_factory=list)
    metric: str = ""
    owner: str = ""
    status: str = "approved"
    verified_at: str = ""
    expects: dict = field(default_factory=dict)
    path: Path | None = None

    def match_score(self, question: str) -> float:
        q = _tokens(question)
        best = 0.0
        for phrase in [self.question, *self.aliases]:
            p = _tokens(phrase)
            if not p:
                continue
            overlap = len(q & p) / len(p)  # fraction of the golden's phrase covered
            best = max(best, overlap)
        return best


def _parse(path: Path) -> Golden | None:
    text = path.read_text()
    m = _FRONTMATTER.match(text)
    if not m:
        return None
    meta = yaml.safe_load(m.group(1)) or {}
    return Golden(
        id=str(meta.get("id", path.stem)),
        question=str(meta.get("question", "")),
        sql=m.group(2).strip(),
        aliases=list(meta.get("aliases", []) or []),
        metric=str(meta.get("metric", "")),
        owner=str(meta.get("owner", "")),
        status=str(meta.get("status", "approved")),
        verified_at=str(meta.get("verified_at", "")),
        expects=dict(meta.get("expects", {}) or {}),
        path=path,
    )


_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _SLUG.sub("_", text.lower()).strip("_")[:60] or "golden"


def save_golden(
    root: Path,
    question: str,
    sql: str,
    *,
    id: str | None = None,
    aliases: list[str] | None = None,
    metric: str = "",
    owner: str = "",
    expects: dict | None = None,
) -> Path:
    """Write a golden `.sql` file with YAML frontmatter. Secret-free, PR-reviewable."""
    gid = id or slug(question)
    d = root / ".opendata" / "golden"
    d.mkdir(parents=True, exist_ok=True)
    header: dict = {
        "id": gid,
        "question": question,
        "aliases": aliases or [],
        "status": "approved",
        "owner": owner,
    }
    if metric:
        header["metric"] = metric
    if expects:
        header["expects"] = expects
    fm = yaml.safe_dump(header, sort_keys=False).strip()
    p = d / f"{gid}.sql"
    p.write_text(f"---\n{fm}\n---\n{sql.strip()}\n")
    return p


def load_goldens(root: Path) -> list[Golden]:
    d = root / ".opendata" / "golden"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.sql")):
        g = _parse(p)
        if g:
            out.append(g)
    return out


def best_match(root: Path, question: str, threshold: float = 0.6) -> Golden | None:
    best, best_score = None, 0.0
    for g in load_goldens(root):
        s = g.match_score(question)
        if s > best_score:
            best, best_score = g, s
    return best if best and best_score >= threshold else None
