import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from journal_kb.config import DEFAULT_CONFIG_PATH, load_config
from journal_kb.digest import build_digest, deliver
from journal_kb.embed import make_embedder
from journal_kb.ingest import run_ingest
from journal_kb.launchd import LAUNCH_AGENTS, plists
from journal_kb.mover import move_uploads
from journal_kb.reader import make_reader
from journal_kb.store import Store
from journal_kb.web import make_server


def _store(cfg) -> Store:
    return Store(cfg.db_path, int(cfg.raw["embed"]["dimensions"]))


def _ingest(cfg) -> int:
    report = run_ingest(cfg, _store(cfg), make_reader(cfg), make_embedder(cfg))
    print(
        f"read {report.pages_read} page(s), skipped {report.pages_skipped} unchanged, removed {report.pages_deleted}; "
        f"tokens {report.input_tokens} in / {report.output_tokens} out; embedded {report.entries_embedded}"
    )
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if report.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journal-kb", description="reMarkable bullet journal -> LLM wiki + search")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("move", help="move notebook uploads from the Drive root into raw/notebooks")
    sub.add_parser("ingest", help="read new or changed pages, embed them, and update the wiki")
    sub.add_parser("run", help="move (if enabled) then ingest; what the scheduled job runs")
    digest = sub.add_parser("digest", help="build the daily digest and deliver it to the configured outputs")
    digest.add_argument("--print", action="store_true", help="print the digest instead of delivering it")
    sub.add_parser("serve", help="run the search page on localhost")
    sub.add_parser("mcp", help="run the MCP server over stdio")
    sub.add_parser("status", help="pages read, tokens used, open tasks")
    launch = sub.add_parser("launchd", help="print (or --write) the launchd jobs for run and digest")
    launch.add_argument("--write", action="store_true", help="write the plists to ~/Library/LaunchAgents")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.command == "move":
        print(f"moved {len(move_uploads(cfg))} upload(s)")
        return 0
    if args.command == "ingest":
        return _ingest(cfg)
    if args.command == "run":
        if cfg.raw["move"]["enabled"]:
            print(f"moved {len(move_uploads(cfg))} upload(s)")
        return _ingest(cfg)
    if args.command == "digest":
        today = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
        store = _store(cfg)
        markdown = build_digest(cfg, store, today)
        if args.print:
            print(markdown)
            return 0
        print(f"delivered to: {', '.join(deliver(cfg, markdown, today)) or 'nothing'}")
        return 0
    if args.command == "serve":
        server = make_server(cfg, _store(cfg), make_embedder(cfg))
        print(f"journal search on http://127.0.0.1:{server.server_address[1]}")
        server.serve_forever()
        return 0
    if args.command == "mcp":
        from journal_kb.mcp_server import build_server

        build_server(cfg, _store(cfg), make_embedder(cfg)).run()
        return 0
    if args.command == "status":
        store = _store(cfg)
        usage = store.usage()
        tasks = len(store.open_tasks())
        print(f"{usage['pages']} page(s) stored; tokens {usage['input_tokens']} in / {usage['output_tokens']} out")
        print(f"{tasks} open task{'s' if tasks != 1 else ''}; database {cfg.db_path}")
        return 0
    if args.command == "launchd":
        executable = shutil.which("journal-kb") or str(Path(sys.executable).parent / "journal-kb")
        jobs = plists(cfg, executable, str(args.config.expanduser().resolve()))
        for label, body in jobs.items():
            path = LAUNCH_AGENTS / f"{label}.plist"
            if args.write:
                (cfg.state_dir / "logs").mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                print(f"wrote {path}\n  load with: launchctl bootstrap gui/$(id -u) '{path}'")
            else:
                print(f"# {path}\n{body.decode()}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
