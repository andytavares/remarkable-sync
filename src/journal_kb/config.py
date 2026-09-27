import copy
import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "journal-kb" / "config.toml"

DEFAULTS = {
    "paths": {
        "wiki_root": "~/Google Drive/My Drive/llm-wiki",
        "drive_root": "~/Google Drive/My Drive",
        "state_dir": "~/.local/share/journal-kb",
    },
    "notebooks": [
        {"match": "* Journal", "kind": "journal"},
        {"match": "1:1 *", "kind": "one_on_one"},
        {"match": "Architecture", "kind": "architecture"},
        {"match": "Future Log", "kind": "future_log"},
    ],
    "reader": {"model": "claude-sonnet-5", "dpi": 150, "api_key_keychain_service": ""},
    "embed": {
        "ollama_url": "http://localhost:11434",
        "model": "nomic-embed-text",
        "dimensions": 768,
        "document_prefix": "search_document: ",
        "query_prefix": "search_query: ",
    },
    "move": {"enabled": True, "min_age_seconds": 60},
    "digest": {
        "outputs": ["wiki", "morning"],
        "include_one_on_ones": False,
        "email": {
            "to": "",
            "username": "",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 465,
            "password_keychain_service": "journal-kb-smtp",
        },
    },
    "signals": {"similarity": 0.68, "window_days": 30},
    "web": {"port": 8765},
}

DIGEST_OUTPUTS = {"wiki", "morning", "email"}
KINDS = {"journal", "one_on_one", "architecture", "future_log"}


class ConfigError(ValueError):
    pass


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _path(value: str) -> Path:
    return Path(value).expanduser()


@dataclass(frozen=True)
class Config:
    raw: dict

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        merged = _merge(DEFAULTS, data)
        for output in merged["digest"]["outputs"]:
            if output not in DIGEST_OUTPUTS:
                raise ConfigError(f"digest.outputs: unknown output {output!r}; use {sorted(DIGEST_OUTPUTS)}")
        if "email" in merged["digest"]["outputs"] and not merged["digest"]["email"]["to"]:
            raise ConfigError("digest.outputs includes 'email' but digest.email.to is empty")
        for nb in merged["notebooks"]:
            if nb.get("kind") not in KINDS:
                raise ConfigError(f"notebooks: {nb.get('match')!r} has unknown kind {nb.get('kind')!r}")
        return cls(merged)

    @property
    def wiki_root(self) -> Path:
        return _path(self.raw["paths"]["wiki_root"])

    @property
    def wiki_dir(self) -> Path:
        return self.wiki_root / "wiki"

    @property
    def raw_notebooks(self) -> Path:
        return self.wiki_root / "raw" / "notebooks"

    @property
    def drive_root(self) -> Path:
        return _path(self.raw["paths"]["drive_root"])

    @property
    def state_dir(self) -> Path:
        return _path(self.raw["paths"]["state_dir"])

    @property
    def db_path(self) -> Path:
        return self.state_dir / "state.db"

    @property
    def reader_model(self) -> str:
        return self.raw["reader"]["model"]

    @property
    def dpi(self) -> int:
        return int(self.raw["reader"]["dpi"])

    @property
    def digest_outputs(self) -> list[str]:
        return list(self.raw["digest"]["outputs"])

    @property
    def include_one_on_ones(self) -> bool:
        return bool(self.raw["digest"]["include_one_on_ones"])

    def kind_of(self, notebook: str) -> str | None:
        for nb in self.raw["notebooks"]:
            if fnmatch.fnmatchcase(notebook, nb["match"]):
                return nb["kind"]
        return None


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Config.from_dict({})
    with path.open("rb") as f:
        return Config.from_dict(tomllib.load(f))
