import plistlib

from conftest import FakeEmbedder, FakeReader, entry, make_pdf, page

from journal_kb import cli
from journal_kb.launchd import plists


def test_plists_schedule_ingest_every_five_minutes_and_digest_on_weekday_mornings(cfg):
    jobs = plists(cfg, executable="/opt/jkb/bin/journal-kb", config_path="/cfg.toml")
    ingest = plistlib.loads(jobs["com.journal-kb.ingest"])
    digest = plistlib.loads(jobs["com.journal-kb.digest"])
    assert ingest["ProgramArguments"] == ["/opt/jkb/bin/journal-kb", "--config", "/cfg.toml", "run"]
    assert ingest["StartInterval"] == 300
    assert digest["ProgramArguments"][-1] == "digest"
    assert [(d["Weekday"], d["Hour"], d["Minute"]) for d in digest["StartCalendarInterval"]] == [
        (1, 7, 0),
        (2, 7, 0),
        (3, 7, 0),
        (4, 7, 0),
        (5, 7, 0),
    ]
    assert ingest["StandardErrorPath"].startswith(str(cfg.state_dir))


def test_run_command_moves_then_ingests(cfg, monkeypatch, capsys):
    import os
    import time

    pdf = make_pdf(cfg.drive_root / "2026-09 Journal.pdf", ["p"])
    old = time.time() - 600
    os.utime(pdf, (old, old))
    reader = FakeReader()
    reader.script(pdf, [page("2026-09-24", [entry("task", "update ADR")])])
    monkeypatch.setattr(cli, "load_config", lambda path: cfg)
    monkeypatch.setattr(cli, "make_reader", lambda c: reader)
    monkeypatch.setattr(cli, "make_embedder", lambda c: FakeEmbedder())

    assert cli.main(["run"]) == 0
    out = capsys.readouterr().out
    assert "moved 1" in out and "read 1 page" in out
    assert (cfg.wiki_dir / "journal" / "2026-09-24.md").exists()

    assert cli.main(["status"]) == 0
    assert "1 open task" in capsys.readouterr().out


def test_digest_print_does_not_deliver(cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path: cfg)
    monkeypatch.setattr(cli, "make_embedder", lambda c: FakeEmbedder())
    assert cli.main(["digest", "--print"]) == 0
    assert "# Journal digest" in capsys.readouterr().out
    assert not (cfg.wiki_dir / "journal" / "digest.md").exists()
