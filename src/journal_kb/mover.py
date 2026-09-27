import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from journal_kb.ingest import DRIVE_DUPLICATE_SUFFIX


def move_uploads(cfg, now: datetime | None = None) -> list[Path]:
    """Move notebook PDFs the tablet uploaded to the Drive root into raw/notebooks/<notebook>/<stamp>.pdf."""
    now = now or datetime.now(UTC).astimezone()
    min_age = float(cfg.raw["move"]["min_age_seconds"])
    stamp = now.strftime("%Y%m%d-%H%M%S")
    moved = []
    for pdf in sorted(cfg.drive_root.glob("*.pdf")):
        notebook = DRIVE_DUPLICATE_SUFFIX.sub("", pdf.stem)
        if not cfg.kind_of(notebook):
            continue
        # Drive for Desktop may still be writing a file it just synced down.
        if time.time() - pdf.stat().st_mtime < min_age:
            continue
        dest_dir = cfg.raw_notebooks / notebook
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{stamp}.pdf"
        n = 2
        while dest.exists():
            dest = dest_dir / f"{stamp}-{n}.pdf"
            n += 1
        shutil.move(pdf, dest)
        moved.append(dest)
    return moved
