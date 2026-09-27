import os
import time

from conftest import FakeEmbedder, FakeReader, entry, event, make_pdf, page

from journal_kb.ingest import run_ingest
from journal_kb.reader import ReadError
from journal_kb.store import Store

TODAY = "2026-09-25"


def journal(cfg, name="2026-09 Journal", stamp="20260924-080000", texts=("p1", "p2")):
    return make_pdf(cfg.raw_notebooks / name / f"{stamp}.pdf", list(texts))


def two_pages():
    return [
        page(
            "2026-09-24",
            [
                entry("event", "Design review: ingest rate limiting", meeting="Design review: ingest rate limiting"),
                entry(
                    "decision",
                    "token bucket per tenant (b/c simpler)",
                    project="ingest",
                    meeting="Design review: ingest rate limiting",
                ),
                entry(
                    "delegated",
                    "load test 10x burst",
                    owner="JM",
                    due="2026-09-26",
                    meeting="Design review: ingest rate limiting",
                ),
            ],
            events=[event("Design review: ingest rate limiting")],
        ),
        page(None, [entry("task", "update ADR", priority=True)]),
    ]


def run(cfg, reader, store):
    return run_ingest(cfg, store, reader, FakeEmbedder(), today=TODAY)


def test_second_run_on_the_same_upload_reads_nothing(cfg):
    pdf = journal(cfg)
    reader = FakeReader()
    reader.script(pdf, two_pages())
    store = Store(cfg.db_path, 768)

    first = run(cfg, reader, store)
    second = run(cfg, reader, store)

    assert (first.pages_read, second.pages_read) == (2, 0)
    assert len(reader.contexts) == 2


def test_a_new_upload_rereads_only_the_edited_page_and_replaces_its_entries(cfg):
    reader = FakeReader()
    store = Store(cfg.db_path, 768)
    old = journal(cfg, stamp="20260924-080000", texts=("p1", "p2"))
    reader.script(old, two_pages())
    run(cfg, reader, store)

    new = journal(cfg, stamp="20260925-080000", texts=("p1", "p2 with × drawn"))
    edited = two_pages()
    edited[1] = page(None, [entry("task", "update ADR", state="done")])
    reader.script(new, edited)
    os.utime(new, (time.time() + 10, time.time() + 10))
    report = run(cfg, reader, store)

    assert report.pages_read == 1
    assert [t["text"] for t in store.open_tasks()] == []


def test_undated_pages_carry_the_previous_pages_date(cfg):
    pdf = journal(cfg)
    reader = FakeReader()
    reader.script(pdf, two_pages())
    store = Store(cfg.db_path, 768)
    run(cfg, reader, store)
    [task] = store.open_tasks()
    assert task["date"] == "2026-09-24"


def test_flat_uploads_with_drive_duplicate_suffix_map_to_the_notebook(cfg):
    pdf = make_pdf(cfg.raw_notebooks / "2026-09 Journal (1).pdf", ["p1", "p2"])
    reader = FakeReader()
    reader.script(pdf, two_pages())
    store = Store(cfg.db_path, 768)
    run(cfg, reader, store)
    assert {t["notebook"] for t in store.open_tasks()} == {"2026-09 Journal"}


def test_pdfs_that_match_no_notebook_are_ignored(cfg):
    make_pdf(cfg.raw_notebooks / "taxes.pdf", ["p1"])
    report = run(cfg, FakeReader(), Store(cfg.db_path, 768))
    assert report.pages_read == 0


def test_the_reader_is_told_which_notebook_and_page_it_is_reading(cfg):
    pdf = journal(cfg)
    reader = FakeReader()
    reader.script(pdf, two_pages())
    run(cfg, reader, Store(cfg.db_path, 768))
    assert "2026-09 Journal" in reader.contexts[1]
    assert "page 2" in reader.contexts[1]
    assert "2026-09-24" in reader.contexts[1]


def test_pages_dropped_from_a_newer_upload_are_removed(cfg):
    reader = FakeReader()
    store = Store(cfg.db_path, 768)
    old = journal(cfg, stamp="20260924-080000", texts=("p1", "p2"))
    reader.script(old, two_pages())
    run(cfg, reader, store)
    new = journal(cfg, stamp="20260925-080000", texts=("p1",))
    reader.script(new, two_pages()[:1])
    os.utime(new, (time.time() + 10, time.time() + 10))
    run(cfg, reader, store)
    assert store.open_tasks() == []


def test_a_failed_page_is_reported_and_retried_on_the_next_run(cfg):
    pdf = journal(cfg)
    reader = FakeReader()
    reader.script(pdf, two_pages())
    store = Store(cfg.db_path, 768)
    real_read = reader.read
    calls = {"n": 0}

    def flaky(png, context):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ReadError("stop_reason=max_tokens")
        return real_read(png, context)

    reader.read = flaky
    first = run(cfg, reader, store)
    second = run(cfg, reader, store)
    assert (first.pages_read, len(first.errors)) == (1, 1)
    assert second.pages_read == 1


def test_entries_and_pages_get_embeddings(cfg):
    pdf = journal(cfg)
    reader = FakeReader()
    reader.script(pdf, two_pages())
    store = Store(cfg.db_path, 768)
    run(cfg, reader, store)
    hits = store.search(FakeEmbedder().embed_query("token bucket tenant"), k=1)
    assert hits[0]["text"] == "token bucket per tenant (b/c simpler)"


def test_bullets_are_embedded_with_their_type_meeting_and_project(cfg):
    pdf = journal(cfg)
    reader = FakeReader()
    reader.script(pdf, two_pages())
    store = Store(cfg.db_path, 768)
    run(cfg, reader, store)
    hits = store.search(FakeEmbedder().embed_query("decision rate limiting"), k=1)
    assert hits[0]["text"] == "token bucket per tenant (b/c simpler)"
