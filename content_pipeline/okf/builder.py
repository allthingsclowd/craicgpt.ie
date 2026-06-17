"""OKF v0.1 builder — pure, stdlib-only (no PyYAML).

Open Knowledge Format (Google, knowledge-catalog/okf/SPEC.md, v0.1 draft) is just
**markdown + YAML frontmatter, one concept file per finding, in a directory
bundle**. The only hard rule: a non-empty ``type:`` in every non-reserved ``.md``;
``index.md`` is a reserved directory listing.

Two layers:

* **Generic core** — :class:`Concept`, :class:`Bundle`, :func:`render_concept`,
  :func:`bundle_files`, :func:`flatten_for_judge`, :func:`validate`,
  :func:`bundle_to_json`/:func:`bundle_from_json`. Mirrors the canonical reference
  in the ``grounding-judges-with-okf`` skill (and geekwiththepeak's copy).
* **craicgpt mapper** — :func:`build_craicgpt_bundle` turns one edition's curated
  research (validated AI candidates + curated fun picks) into concepts.

Why this exists: the rubric judge graded the edition against its TRAINING DATA, so a
fresh story it hadn't seen read as "made up". The flattened bundle becomes the
judge's ground truth — it confirms the desk is substantive and real instead of
guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

OKF_VERSION = "0.1"


# --- core data model ---------------------------------------------------------


@dataclass
class Concept:
    """One unit of knowledge = one markdown file. ``concept_id`` is the file path
    within the bundle, minus ``.md`` (e.g. ``ai/00-some-story``)."""

    concept_id: str
    type: str
    title: str = ""
    description: str = ""
    resource: str = ""
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""
    body: str = ""
    citations: list[str] = field(default_factory=list)


@dataclass
class Bundle:
    concepts: list[Concept]
    version: str = OKF_VERSION
    name: str = ""
    description: str = ""


# --- frontmatter emission (hand-rolled, deterministic) -----------------------


def _scalar(value: str) -> str:
    """A YAML plain scalar, single-quoted only when YAML would mis-parse it."""
    s = str(value)
    if s == "":
        return "''"
    risky = (
        s != s.strip()
        or ": " in s
        or s.endswith(":")
        or " #" in s
        or "\n" in s
        or s[0] in "#&*!|>%@`\"'[]{},?:-"
    )
    return "'" + s.replace("'", "''") + "'" if risky else s


def render_concept(c: Concept) -> str:
    """Render one concept to an OKF markdown document. Raises if ``type`` is empty —
    the single OKF hard requirement."""
    if not c.type.strip():
        raise ValueError(f"OKF concept {c.concept_id!r} has an empty 'type'")
    lines = ["---", f"type: {_scalar(c.type)}"]
    if c.title:
        lines.append(f"title: {_scalar(c.title)}")
    if c.description:
        lines.append(f"description: {_scalar(c.description)}")
    if c.resource:
        lines.append(f"resource: {_scalar(c.resource)}")
    if c.tags:
        lines.append("tags:")
        lines.extend(f"- {_scalar(t)}" for t in c.tags)
    if c.timestamp:
        lines.append(f"timestamp: '{c.timestamp}'")
    lines.append("---")
    fm = "\n".join(lines)
    body = (c.body or "").strip("\n")
    doc = f"{fm}\n\n{body}\n" if body else f"{fm}\n"
    if c.citations:
        cites = "\n".join(f"- {u}" for u in c.citations)
        doc += f"\n# Citations\n{cites}\n"
    return doc


def render_index(title: str, entries: list[tuple[str, str, str]], *, root: bool = False,
                 version: str = OKF_VERSION) -> str:
    """A reserved ``index.md`` directory listing. The bundle root MAY carry
    ``okf_version``; sub-directory indexes carry none."""
    lines: list[str] = []
    if root:
        lines += ["---", f'okf_version: "{version}"', "---", ""]
    lines += [f"# {title}", ""]
    for rel, label, desc in entries:
        lines.append(f"* [{label}]({rel})" + (f" - {desc}" if desc else ""))
    return "\n".join(lines) + "\n"


def bundle_files(b: Bundle) -> dict[str, str]:
    """Render the bundle to a ``{path: content}`` tree, including a reserved
    ``index.md`` at the root and in every sub-directory."""
    files: dict[str, str] = {}
    by_dir: dict[str, list[Concept]] = {}
    for c in b.concepts:
        files[f"{c.concept_id}.md"] = render_concept(c)
        d = c.concept_id.rsplit("/", 1)[0] if "/" in c.concept_id else ""
        by_dir.setdefault(d, []).append(c)

    for d, concepts in by_dir.items():
        if not d:
            continue
        entries = [
            (f"{c.concept_id.rsplit('/', 1)[-1]}.md", c.title or c.concept_id, c.description)
            for c in concepts
        ]
        files[f"{d}/index.md"] = render_index(d, entries)

    root_entries = [(f"{d}/index.md", d, "") for d in sorted(by_dir) if d]
    files["index.md"] = render_index(b.name or "Knowledge Bundle", root_entries,
                                     root=True, version=b.version)
    return files


def flatten_for_judge(b: Bundle, *, budget: int = 6000) -> str:
    """Concatenate the bundle's concepts into ONE budgeted block for a one-shot
    judge (which cannot navigate ``index.md`` progressive disclosure)."""
    blocks: list[str] = []
    for c in b.concepts:
        head = f"### {c.concept_id} ({c.type})"
        meta = []
        if c.title:
            meta.append(c.title)
        if c.resource:
            meta.append(f"source: {c.resource}")
        body = (c.body or "").strip()
        blocks.append("\n".join([head, *meta, body]).strip())
    out = "\n\n".join(blocks).strip()
    return out if len(out) <= budget else out[: budget - 1] + "…"


# --- conformance + json persistence -----------------------------------------


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return None
    fm: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i] != "---":
        line = lines[i]
        if ":" in line and not line.startswith("- "):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
        i += 1
    if i >= len(lines):
        return None
    return fm


def validate(files: dict[str, str]) -> list[str]:
    """OKF v0.1 conformance: every non-reserved ``.md`` has parseable frontmatter
    with a non-empty ``type``. Returns a list of problems (empty == conformant)."""
    problems: list[str] = []
    for path, content in sorted(files.items()):
        if not path.endswith(".md"):
            continue
        base = path.rsplit("/", 1)[-1]
        if base in ("index.md", "log.md"):
            continue
        fm = _parse_frontmatter(content)
        if fm is None:
            problems.append(f"{path}: missing/unparseable frontmatter")
        elif not fm.get("type", "").strip():
            problems.append(f"{path}: missing non-empty 'type'")
    return problems


def bundle_to_json(b: Bundle) -> dict[str, Any]:
    return {
        "okf_version": b.version,
        "name": b.name,
        "description": b.description,
        "concepts": [
            {
                "concept_id": c.concept_id,
                "type": c.type,
                "title": c.title,
                "description": c.description,
                "resource": c.resource,
                "tags": list(c.tags),
                "timestamp": c.timestamp,
                "body": c.body,
                "citations": list(c.citations),
            }
            for c in b.concepts
        ],
    }


def bundle_from_json(data: dict[str, Any]) -> Bundle:
    return Bundle(
        version=data.get("okf_version", OKF_VERSION),
        name=data.get("name", ""),
        description=data.get("description", ""),
        concepts=[
            Concept(
                concept_id=d["concept_id"],
                type=d["type"],
                title=d.get("title", ""),
                description=d.get("description", ""),
                resource=d.get("resource", ""),
                tags=list(d.get("tags", [])),
                timestamp=d.get("timestamp", ""),
                body=d.get("body", ""),
                citations=list(d.get("citations", [])),
            )
            for d in data.get("concepts", [])
        ],
    )


# --- craicgpt mapper ---------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    s = _SLUG_RE.sub("-", str(text or "").lower()).strip("-")
    return s or "item"


def _clip(text: str, n: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _attr(obj: Any, key: str) -> Any:
    """Read ``key`` from a dict OR a dataclass (curation Story) uniformly."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def ai_story_concept(c: dict[str, Any], i: int) -> Concept:
    """One validated AI candidate → an ``AI Story`` concept carrying the research
    the writer was handed: why-it-matters, the key points, and the conclusion."""
    key_points = c.get("key_points") or []
    parts: list[str] = []
    if c.get("why_it_matters"):
        parts.append(str(c["why_it_matters"]))
    if key_points:
        parts.append("Key points:\n" + "\n".join(f"- {p}" for p in key_points))
    if c.get("conclusion"):
        parts.append(str(c["conclusion"]))
    return Concept(
        concept_id=f"ai/{i:02d}-{_slug(c.get('title', ''))}",
        type="AI Story",
        title=c.get("title", ""),
        description=_clip(c.get("summary", ""), 140),
        resource=c.get("source_url", ""),
        body="\n\n".join(parts) or c.get("summary", ""),
        citations=[u for u in [c.get("source_url", "")] if u],
    )


def fun_story_concept(s: Any, i: int) -> Concept:
    """One curated fun pick (a curation ``Story`` or dict) → a ``Fun Story``
    concept. Carries the creator credit so the judge can confirm attribution."""
    title = _attr(s, "title") or ""
    url = _attr(s, "source_url") or ""
    creator = _attr(s, "creator") or ""
    category = _attr(s, "category") or ""
    return Concept(
        concept_id=f"fun/{i:02d}-{_slug(title)}",
        type="Fun Story",
        title=title,
        description=_clip(_attr(s, "summary") or "", 140),
        resource=url,
        tags=[t for t in [category, creator] if t],
        body=_attr(s, "summary") or "",
        citations=[u for u in [url] if u],
    )


def build_craicgpt_bundle(ai_valid: list, fun_picks: list, *, date: str = "") -> Bundle | None:
    """Build the OKF bundle for one edition from its CURATED research — the
    link-validated AI candidates and the curated fun picks the articles are
    written from. Returns ``None`` when there is no research at all (an empty
    bundle would read as "every claim unsupported")."""
    concepts: list[Concept] = []
    for i, c in enumerate(ai_valid or []):
        if isinstance(c, dict):
            concepts.append(ai_story_concept(c, i))
    for i, s in enumerate(fun_picks or []):
        concepts.append(fun_story_concept(s, i))
    if not concepts:
        return None
    return Bundle(
        concepts=concepts,
        name=f"CraicGPT research grounding — {date}".strip(" —"),
        description="Code-verified, link-validated research (curated AI + fun "
        "candidates) behind today's edition.",
    )
