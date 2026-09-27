from pathlib import Path

import pytest

from journal_kb.config import Config, ConfigError, load_config


def test_defaults_cover_the_four_notebook_kinds(cfg):
    assert cfg.kind_of("2026-09 Journal") == "journal"
    assert cfg.kind_of("1:1 KP") == "one_on_one"
    assert cfg.kind_of("Architecture") == "architecture"
    assert cfg.kind_of("Future Log") == "future_log"
    assert cfg.kind_of("Shopping list") is None


def test_paths_expand_home():
    c = Config.from_dict({"paths": {"wiki_root": "~/w"}})
    assert c.wiki_root == Path.home() / "w"
    assert c.raw_notebooks == Path.home() / "w" / "raw" / "notebooks"


def test_unknown_digest_output_is_rejected():
    with pytest.raises(ConfigError, match="fax"):
        Config.from_dict({"digest": {"outputs": ["wiki", "fax"]}})


def test_email_output_requires_an_address():
    with pytest.raises(ConfigError, match="digest.email.to"):
        Config.from_dict({"digest": {"outputs": ["email"]}})


def test_load_config_reads_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[reader]\nmodel = "claude-opus-5"\n[digest]\noutputs = ["wiki"]\n')
    c = load_config(p)
    assert c.reader_model == "claude-opus-5"
    assert c.digest_outputs == ["wiki"]


def test_missing_config_file_falls_back_to_defaults(tmp_path):
    c = load_config(tmp_path / "nope.toml")
    assert c.reader_model == "claude-sonnet-5"
    assert c.digest_outputs == ["wiki", "morning"]
