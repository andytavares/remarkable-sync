from typing import ClassVar

from conftest import FakeEmbedder, FakeReader, entry, make_pdf, page

from journal_kb.config import Config
from journal_kb.digest import build_digest, deliver, previous_business_day
from journal_kb.ingest import run_ingest
from journal_kb.store import Store


def seeded(cfg):
    reader = FakeReader()
    j = make_pdf(cfg.raw_notebooks / "2026-09 Journal" / "20260928-080000.pdf", ["a", "b", "c"])
    reader.script(
        j,
        [
            page("2026-09-24", [entry("task", "update ADR"), entry("decision", "old decision on thursday")]),
            page(
                "2026-09-25",
                [
                    entry("task", "already done", state="done"),
                    entry("task", "migrated to linear", state="migrated"),
                    entry("delegated", "load test 10x burst", owner="JM", due="2026-09-29"),
                    entry("decision", "token bucket per tenant"),
                    entry("note", "third service with its own rate limiter", signal=True),
                    entry("question", "smudged line", confidence="low"),
                ],
            ),
            page(
                "2026-09-28",
                [
                    entry("note", "another service with its own rate limiter", signal=True),
                    entry("note", "hiring plan", signal=True),
                ],
            ),
        ],
    )
    o = make_pdf(cfg.raw_notebooks / "1:1 KP" / "20260928-080000.pdf", ["o"])
    reader.script(o, [page("2026-09-25", [entry("task", "write KP promo packet")])])
    store = Store(cfg.db_path, 768)
    run_ingest(cfg, store, reader, FakeEmbedder(), today="2026-09-28")
    return store


def test_previous_business_day_skips_the_weekend():
    assert previous_business_day("2026-09-28") == "2026-09-25"  # Monday -> Friday
    assert previous_business_day("2026-09-30") == "2026-09-29"


def test_digest_sections(cfg):
    md = build_digest(cfg, seeded(cfg), today="2026-09-28")
    tasks = md.split("## Your open tasks")[1].split("##")[0]
    assert "update ADR" in tasks and "4 days" in tasks
    assert "already done" not in md and "migrated to linear" not in md
    assert "JM: load test 10x burst (due 2026-09-29)" in md
    decisions = md.split("## Decisions since")[1].split("##")[0]
    assert "token bucket per tenant" in decisions
    assert "old decision on thursday" not in decisions
    recurring = md.split("## Recurring signals")[1].split("##")[0]
    assert "rate limiter" in recurring and "(2×)" in recurring
    assert "hiring plan" not in recurring
    assert "smudged line" in md.split("## Needs a look")[1]


def test_one_on_ones_are_counted_not_shown_unless_enabled(cfg):
    store = seeded(cfg)
    hidden = build_digest(cfg, store, today="2026-09-28")
    assert "promo packet" not in hidden
    assert "1 open task in 1:1 notebooks" in hidden
    shown_cfg = Config.from_dict({**cfg.raw, "digest": {"include_one_on_ones": True}})
    assert "promo packet" in build_digest(shown_cfg, store, today="2026-09-28")


class RecordingSMTP:
    sent: ClassVar[list] = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.user = user

    def send_message(self, msg):
        RecordingSMTP.sent.append(msg)


def test_deliver_writes_the_wiki_page_and_emails_when_both_are_enabled(cfg):
    c = Config.from_dict(
        {
            **cfg.raw,
            "digest": {"outputs": ["wiki", "email"], "email": {"to": "me@example.com", "username": "me@example.com"}},
        }
    )
    RecordingSMTP.sent = []
    written = deliver(
        c,
        "# Journal digest\n\n- item\n",
        today="2026-09-28",
        smtp_class=RecordingSMTP,
        password_lookup=lambda svc, user: "pw",
    )
    page_text = (c.wiki_root / "wiki" / "journal" / "digest.md").read_text()
    assert page_text.startswith("---\ntype: journal\n") and "- item" in page_text
    [msg] = RecordingSMTP.sent
    assert msg["To"] == "me@example.com" and "2026-09-28" in msg["Subject"]
    assert written == ["wiki", "email"]


def test_morning_output_alone_still_writes_the_page_the_brief_reads(cfg):
    c = Config.from_dict({**cfg.raw, "digest": {"outputs": ["morning"]}})
    assert deliver(c, "# d\n", today="2026-09-28") == ["morning"]
    assert (c.wiki_root / "wiki" / "journal" / "digest.md").exists()
