import os
import time
from datetime import UTC, datetime

from conftest import make_pdf

from journal_kb.mover import move_uploads

NOW = datetime(2026, 9, 27, 7, 0, 0, tzinfo=UTC)


def aged(path, seconds=600):
    t = time.time() - seconds
    os.utime(path, (t, t))
    return path


def test_notebook_uploads_move_into_raw_as_timestamped_snapshots(cfg):
    aged(make_pdf(cfg.drive_root / "2026-09 Journal.pdf", ["p"]))
    aged(make_pdf(cfg.drive_root / "1:1 KP (1).pdf", ["p"]))
    moved = move_uploads(cfg, now=NOW)
    assert sorted(p.relative_to(cfg.raw_notebooks).as_posix() for p in moved) == [
        "1:1 KP/20260927-070000.pdf",
        "2026-09 Journal/20260927-070000.pdf",
    ]
    assert not (cfg.drive_root / "2026-09 Journal.pdf").exists()


def test_other_pdfs_and_files_still_syncing_are_left_alone(cfg):
    aged(make_pdf(cfg.drive_root / "taxes.pdf", ["p"]))
    make_pdf(cfg.drive_root / "Architecture.pdf", ["p"])  # just written
    assert move_uploads(cfg, now=NOW) == []
    assert (cfg.drive_root / "taxes.pdf").exists()
    assert (cfg.drive_root / "Architecture.pdf").exists()


def test_a_second_upload_in_the_same_second_does_not_overwrite(cfg):
    aged(make_pdf(cfg.drive_root / "Architecture.pdf", ["one"]))
    move_uploads(cfg, now=NOW)
    aged(make_pdf(cfg.drive_root / "Architecture.pdf", ["two"]))
    [second] = move_uploads(cfg, now=NOW)
    assert second.name == "20260927-070000-2.pdf"
