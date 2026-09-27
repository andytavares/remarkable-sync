import hashlib
import math
import re
from pathlib import Path

import pymupdf
import pytest

from journal_kb.config import Config
from journal_kb.models import Entry, Event, PageRead
from journal_kb.pdf import render_pages
from journal_kb.reader import ReadResult


def make_pdf(path: Path, texts: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for text in texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    return path


def entry(bullet="task", text="do the thing", **kw) -> Entry:
    fields = {
        "bullet": bullet,
        "signal": False,
        "priority": False,
        "state": "open",
        "text": text,
        "owner": None,
        "due": None,
        "project": None,
        "meeting": None,
        "confidence": "high",
    }
    fields.update(kw)
    return Entry(**fields)


def page(date, entries, events=(), transcription="") -> PageRead:
    return PageRead(
        date=date,
        events=list(events),
        entries=list(entries),
        transcription=transcription or "\n".join(e.text for e in entries),
    )


def event(title, time="10:00", people=("KP",)) -> Event:
    return Event(time=time, title=title, people=list(people))


class FakeReader:
    """Returns a scripted PageRead for each rendered page, keyed by the page's hash."""

    def __init__(self):
        self.by_hash: dict[str, PageRead] = {}
        self.contexts: list[str] = []

    def script(self, pdf: Path, pages: list[PageRead], dpi: int = 72):
        for rendered, read in zip(render_pages(pdf, dpi), pages, strict=True):
            self.by_hash[rendered.sha256] = read

    def read(self, png: bytes, context: str) -> ReadResult:
        self.contexts.append(context)
        return ReadResult(self.by_hash[hashlib.sha256(png).hexdigest()], 1000, 200)


class FakeEmbedder:
    """Bag-of-words hashing embedder: texts that share words land close together."""

    dimensions = 768

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    wiki_root = tmp_path / "llm-wiki"
    (wiki_root / "wiki" / "projects").mkdir(parents=True)
    (wiki_root / "raw" / "notebooks").mkdir(parents=True)
    (wiki_root / "wiki" / "index.md").write_text(
        "---\ndate_updated: 2026-06-22\n---\n\n# Wiki Index\n\n## Concepts\n| Page | Domain | Added |\n"
    )
    (wiki_root / "wiki" / "log.md").write_text("# Wiki Activity Log\n\n## [2026-06-22] older entry\n- kept\n")
    (tmp_path / "drive").mkdir()
    return Config.from_dict(
        {
            "paths": {
                "wiki_root": str(wiki_root),
                "drive_root": str(tmp_path / "drive"),
                "state_dir": str(tmp_path / "state"),
            },
            "reader": {"dpi": 72},
        }
    )
