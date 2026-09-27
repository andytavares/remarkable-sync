import re

from conftest import FakeEmbedder, FakeReader, entry, event, make_pdf, page

from journal_kb.ingest import run_ingest
from journal_kb.store import Store

TODAY = "2026-09-25"
MEETING = "Design review: ingest rate limiting"


def ingest_journal_and_one_on_one(cfg):
    reader = FakeReader()
    j = make_pdf(cfg.raw_notebooks / "2026-09 Journal" / "20260924-080000.pdf", ["j1"])
    reader.script(
        j,
        [
            page(
                "2026-09-24",
                [
                    entry("event", MEETING, meeting=MEETING),
                    entry("decision", "token bucket per tenant", project="ingest", meeting=MEETING),
                    entry("note", "3rd svc w/ own limiter -> shared lib?", signal=True, meeting=MEETING),
                    entry("delegated", "load test 10x burst", owner="JM", due="2026-09-26", meeting=MEETING),
                ],
                events=[event(MEETING)],
            )
        ],
    )
    o = make_pdf(cfg.raw_notebooks / "1:1 KP" / "20260924-080000.pdf", ["o1"])
    reader.script(
        o,
        [page("2026-09-24", [entry("decision", "KP moves to platform team"), entry("task", "write KP promo packet")])],
    )
    store = Store(cfg.db_path, 768)
    run_ingest(cfg, store, reader, FakeEmbedder(), today=TODAY)
    return store, reader


def wiki(cfg, rel):
    return (cfg.wiki_root / "wiki" / rel).read_text()


def test_journal_day_page_has_frontmatter_meeting_sections_and_source_links(cfg):
    ingest_journal_and_one_on_one(cfg)
    text = wiki(cfg, "journal/2026-09-24.md")
    assert text.startswith("---\ntype: journal\n")
    assert "date_updated: 2026-09-25" in text
    assert "sources: [raw/notebooks/2026-09 Journal/20260924-080000.pdf]" in text
    assert f"## {MEETING}" in text
    assert "◇ token bucket per tenant" in text
    assert "→ JM load test 10x burst (due 2026-09-26)" in text
    assert "[[ingest]]" in text
    assert "raw/notebooks/2026-09 Journal/20260924-080000.pdf#page=1" in text


def test_one_on_one_notebooks_never_reach_the_wiki(cfg):
    ingest_journal_and_one_on_one(cfg)
    everything = "".join(p.read_text() for p in (cfg.wiki_root / "wiki").rglob("*.md"))
    assert "KP moves to platform team" not in everything
    assert "promo packet" not in everything


def test_decision_log_and_signals_pages_link_back_to_the_day(cfg):
    ingest_journal_and_one_on_one(cfg)
    log = wiki(cfg, "insights/decision-log.md")
    assert "| 2026-09-24 | token bucket per tenant | [[ingest]] | [[2026-09-24]] |" in log
    assert "3rd svc w/ own limiter" in wiki(cfg, "insights/signals.md")


def test_index_block_and_log_entry_are_written_once_per_change(cfg):
    store, reader = ingest_journal_and_one_on_one(cfg)
    run_ingest(cfg, store, reader, FakeEmbedder(), today=TODAY)
    index = wiki(cfg, "index.md")
    assert index.count("<!-- journal-kb:start -->") == 1
    assert "[[2026-09-24]]" in index
    assert "date_updated: 2026-09-25" in index
    log = wiki(cfg, "log.md")
    assert len(re.findall(r"## \[2026-09-25\] ingest \| journal", log)) == 1
    assert "## [2026-06-22] older entry" in log


def test_existing_project_pages_get_a_decisions_block_that_is_replaced_not_stacked(cfg):
    project = cfg.wiki_root / "wiki" / "projects" / "ingest.md"
    project.write_text("---\ntype: project\n---\n\n# Ingest\n\nHand-written notes.\n")
    store, reader = ingest_journal_and_one_on_one(cfg)
    run_ingest(cfg, store, reader, FakeEmbedder(), today="2026-09-26")
    text = project.read_text()
    assert "Hand-written notes." in text
    assert text.count("<!-- journal-kb:decisions:start -->") == 1
    assert "2026-09-24: token bucket per tenant ([[2026-09-24]])" in text


def test_a_second_changed_ingest_replaces_generated_blocks_instead_of_stacking_them(cfg):
    import os
    import time

    project = cfg.wiki_root / "wiki" / "projects" / "ingest.md"
    project.write_text("# Ingest\n")
    store, reader = ingest_journal_and_one_on_one(cfg)
    newer = make_pdf(cfg.raw_notebooks / "2026-09 Journal" / "20260925-080000.pdf", ["j1 edited"])
    reader.script(newer, [page("2026-09-24", [entry("decision", "token bucket per tenant v2", project="ingest")])])
    os.utime(newer, (time.time() + 10, time.time() + 10))
    run_ingest(cfg, store, reader, FakeEmbedder(), today="2026-09-26")

    assert wiki(cfg, "index.md").count("<!-- journal-kb:start -->") == 1
    text = project.read_text()
    assert text.count("<!-- journal-kb:decisions:start -->") == 1
    assert "token bucket per tenant v2" in text
    assert "token bucket per tenant (" not in text
    assert len(re.findall(r"ingest \| journal", wiki(cfg, "log.md"))) == 2
