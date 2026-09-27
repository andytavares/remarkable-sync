import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class RenderedPage:
    page_no: int
    png: bytes
    sha256: str


def render_pages(pdf: Path | str, dpi: int) -> Iterator[RenderedPage]:
    with pymupdf.open(pdf) as doc:
        for index, page in enumerate(doc):
            png = page.get_pixmap(dpi=dpi).tobytes("png")
            yield RenderedPage(index + 1, png, hashlib.sha256(png).hexdigest())


def render_page(pdf: Path | str, page_no: int, dpi: int) -> bytes:
    with pymupdf.open(pdf) as doc:
        return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")
