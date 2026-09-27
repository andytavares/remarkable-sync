from conftest import make_pdf

from journal_kb.pdf import render_page, render_pages


def test_hash_is_stable_across_renders(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", ["one", "two"])
    first = [p.sha256 for p in render_pages(pdf, 72)]
    second = [p.sha256 for p in render_pages(pdf, 72)]
    assert first == second
    assert first[0] != first[1]


def test_editing_one_page_changes_only_that_hash(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["one", "two", "three"])
    b = make_pdf(tmp_path / "b.pdf", ["one", "two EDITED", "three"])
    ha = [p.sha256 for p in render_pages(a, 72)]
    hb = [p.sha256 for p in render_pages(b, 72)]
    assert [x == y for x, y in zip(ha, hb)] == [True, False, True]


def test_pages_are_numbered_from_one_and_render_png(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", ["one", "two"])
    pages = list(render_pages(pdf, 72))
    assert [p.page_no for p in pages] == [1, 2]
    assert pages[0].png.startswith(b"\x89PNG")
    assert render_page(pdf, 2, 72) == pages[1].png
