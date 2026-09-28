import os
from types import SimpleNamespace

import pytest
from conftest import entry, page

from journal_kb.models import PageRead
from journal_kb.reader import KEY_PROMPT, ClaudeReader, ReadError


class RecordingMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def reader_returning(stop_reason, parsed):
    response = SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1500, output_tokens=300),
    )
    messages = RecordingMessages(response)
    return ClaudeReader(SimpleNamespace(messages=messages), "claude-sonnet-5"), messages


def test_sends_the_page_image_before_the_context_and_keeps_usage():
    reader, messages = reader_returning("end_turn", page("2026-09-24", [entry()]))
    result = reader.read(b"\x89PNGfake", "Notebook: 2026-09 Journal")
    content = messages.kwargs["messages"][0]["content"]
    assert [block["type"] for block in content] == ["image", "text"]
    assert content[0]["source"]["media_type"] == "image/png"
    assert messages.kwargs["output_format"] is PageRead
    assert (result.input_tokens, result.output_tokens) == (1500, 300)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_incomplete_reads_raise_instead_of_returning_partial_pages(stop_reason):
    reader, _ = reader_returning(stop_reason, None)
    with pytest.raises(ReadError, match=stop_reason):
        reader.read(b"png", "ctx")


def test_key_prompt_still_reads_the_old_diamond_as_a_decision():
    assert "◇" in KEY_PROMPT.split("△ decision")[1].split("\n")[0]


def test_key_prompt_names_every_symbol_in_the_key():
    for symbol in ["•", "→", "○", "△", "?", "–", "!", "*", "×", ">", "<", "~~~"]:
        assert symbol in KEY_PROMPT


@pytest.mark.skipif(
    not os.environ.get("JOURNAL_KB_LIVE_PDF"),
    reason="set JOURNAL_KB_LIVE_PDF to a real journal PDF to call the Claude API",
)
def test_live_read_of_a_real_journal_page():
    from journal_kb.config import load_config
    from journal_kb.pdf import render_page
    from journal_kb.reader import make_reader

    # Page 1 is the Key and page 2 the Monthly Log in the primer's layout; daily logs start at 3.
    page_no = int(os.environ.get("JOURNAL_KB_LIVE_PAGE", "3"))
    cfg = load_config()
    png = render_page(os.environ["JOURNAL_KB_LIVE_PDF"], page_no, cfg.dpi)
    context = f"Notebook: 2026-09 Journal (journal), page {page_no}. Previous page's date: unknown."
    result = make_reader(cfg).read(png, context)
    print(result.page.model_dump_json(indent=2))
    print(
        f"page {page_no}: {len(result.page.entries)} entries; tokens {result.input_tokens} in / {result.output_tokens} out"
    )
    assert result.page.transcription.strip()
    assert result.input_tokens > 0
