import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import httpx

from journal_kb.pdf import render_pages
from journal_kb.reader import ReadError
from journal_kb.store import Store
from journal_kb.wiki import WikiWriter

DRIVE_DUPLICATE_SUFFIX = re.compile(r" \(\d+\)$")
EMBED_BATCH = 64


@dataclass(frozen=True)
class Snapshot:
    path: Path
    notebook: str
    kind: str
    mtime: float


@dataclass
class IngestReport:
    pages_read: int = 0
    pages_skipped: int = 0
    pages_deleted: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    entries_embedded: int = 0
    notebooks: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.pages_read or self.pages_deleted)


def notebook_name(pdf: Path, raw_notebooks: Path) -> str:
    if pdf.parent == raw_notebooks:
        return DRIVE_DUPLICATE_SUFFIX.sub("", pdf.stem)
    return pdf.parent.name


def discover(cfg) -> list[Snapshot]:
    found = []
    if not cfg.raw_notebooks.exists():
        return found
    for pdf in cfg.raw_notebooks.rglob("*.pdf"):
        notebook = notebook_name(pdf, cfg.raw_notebooks)
        kind = cfg.kind_of(notebook)
        if kind:
            found.append(Snapshot(pdf, notebook, kind, pdf.stat().st_mtime))
    return sorted(found, key=lambda s: (s.mtime, str(s.path)))


def _ingest_snapshot(cfg, store: Store, reader, snap: Snapshot, report: IngestReport) -> bool:
    ok = True
    page_count = 0
    previous_date = None
    for rendered in render_pages(snap.path, cfg.dpi):
        page_count = rendered.page_no
        if store.page_hash(snap.notebook, rendered.page_no) == rendered.sha256:
            report.pages_skipped += 1
            previous_date = store.page_date(snap.notebook, rendered.page_no) or previous_date
            continue
        context = (
            f"Notebook: {snap.notebook} ({snap.kind}), page {rendered.page_no}. "
            f"Previous page's date: {previous_date or 'unknown'}."
        )
        try:
            result = reader.read(rendered.png, context)
        except (ReadError, anthropic.APIError) as exc:
            report.errors.append(f"{snap.path.name} page {rendered.page_no}: {exc}")
            ok = False
            continue
        date = result.page.date or previous_date
        store.upsert_page(
            notebook=snap.notebook,
            kind=snap.kind,
            page_no=rendered.page_no,
            sha256=rendered.sha256,
            pdf_path=str(snap.path),
            date=date,
            read=result.page,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        previous_date = date
        report.pages_read += 1
        report.input_tokens += result.input_tokens
        report.output_tokens += result.output_tokens
        report.notebooks.add(snap.notebook)
    report.pages_deleted += store.delete_pages_after(snap.notebook, page_count)
    return ok


BULLET_LABEL = {
    "task": "My task",
    "delegated": "Task owned by someone else",
    "event": "Meeting",
    "decision": "Decision",
    "question": "Open question",
    "note": "Note",
}


def embedding_text(e: dict) -> str:
    text = f"{BULLET_LABEL[e['bullet']]}: {e['text']}"
    if e["signal"]:
        text = "Signal. " + text
    if e["owner"]:
        text += f" (owner {e['owner']})"
    if e["meeting"] and e["meeting"] != e["text"]:
        text += f". Meeting: {e['meeting']}"
    if e["project"]:
        text += f". Project: {e['project']}"
    return text


def _embed_pending(store: Store, embedder, report: IngestReport) -> None:
    pending = store.unembedded()
    for start in range(0, len(pending), EMBED_BATCH):
        batch = pending[start : start + EMBED_BATCH]
        try:
            vectors = embedder.embed_documents([embedding_text(e) for e in batch])
        except httpx.HTTPError as exc:
            report.errors.append(f"embedding skipped, will retry next run: {exc}")
            return
        store.set_vectors(list(zip(batch, vectors)))
        report.entries_embedded += len(batch)


def run_ingest(cfg, store: Store, reader, embedder, today: str | None = None) -> IngestReport:
    today = today or datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
    report = IngestReport()
    for snap in discover(cfg):
        if store.snapshot_done(str(snap.path), snap.mtime):
            continue
        if _ingest_snapshot(cfg, store, reader, snap, report):
            store.mark_snapshot(str(snap.path), snap.mtime, today)
    _embed_pending(store, embedder, report)
    if report.changed:
        WikiWriter(cfg, store).write(today, report)
    return report
