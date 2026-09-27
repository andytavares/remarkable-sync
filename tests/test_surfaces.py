import asyncio
import json
import threading
import urllib.request

import pytest
from conftest import FakeEmbedder, FakeReader, entry, make_pdf, page

from journal_kb import queries
from journal_kb.ingest import run_ingest
from journal_kb.mcp_server import build_server
from journal_kb.store import Store
from journal_kb.web import make_server


@pytest.fixture
def store(cfg):
    reader = FakeReader()
    pdf = make_pdf(cfg.raw_notebooks / "2026-09 Journal" / "20260924-080000.pdf", ["p"])
    reader.script(
        pdf,
        [
            page(
                "2026-09-24",
                [
                    entry("decision", "token bucket per tenant", project="ingest"),
                    entry("delegated", "load test 10x burst", owner="JM"),
                    entry("task", "update ADR"),
                    entry("note", "shared rate limiter lib?", signal=True),
                ],
            )
        ],
    )
    s = Store(cfg.db_path, 768)
    run_ingest(cfg, s, reader, FakeEmbedder(), today="2026-09-25")
    return s


def test_queries_answer_the_four_questions(store):
    emb = FakeEmbedder()
    assert queries.search_notes(store, emb, "token bucket")[0]["text"] == "token bucket per tenant"
    assert [t["text"] for t in queries.open_tasks(store)] == ["update ADR"]
    assert [t["text"] for t in queries.open_tasks(store, owner="JM")] == ["load test 10x burst"]
    assert [d["text"] for d in queries.decisions(store, project="ingest")] == ["token bucket per tenant"]
    assert [s["text"] for s in queries.signals(store)] == ["shared rate limiter lib?"]
    assert queries.page(store, 1)["notebook"] == "2026-09 Journal"


def test_mcp_server_exposes_the_query_tools(cfg, store):
    server = build_server(cfg, store, FakeEmbedder())
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"search_notes", "open_tasks", "decisions", "signals", "page"}


def test_search_page_serves_html_json_and_page_images_on_localhost(cfg, store):
    server = make_server(cfg, store, FakeEmbedder(), port=0)
    assert server.server_address[0] == "127.0.0.1"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"<form" in urllib.request.urlopen(base + "/").read()
        results = json.loads(urllib.request.urlopen(base + "/api/search?q=token+bucket").read())
        assert results[0]["text"] == "token bucket per tenant"
        png = urllib.request.urlopen(base + f"/page/{results[0]['page_id']}.png").read()
        assert png.startswith(b"\x89PNG")
    finally:
        server.shutdown()
