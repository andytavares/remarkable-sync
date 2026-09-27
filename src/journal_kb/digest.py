import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

from journal_kb.reader import keychain_password
from journal_kb.signals import cluster
from journal_kb.wiki import format_entry


def _d(s: str) -> date:
    return date.fromisoformat(s)


def previous_business_day(today: str) -> str:
    day = _d(today) - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def _where(p: str) -> str:
    return f"{p['date'] or 'undated'}, {p['notebook']} p{p['page_no']}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def build_digest(cfg, store, today: str) -> str:
    include = cfg.include_one_on_ones
    kind_filter = "" if include else " AND p.kind != 'one_on_one'"
    since = previous_business_day(today)
    lines = [f"# Journal digest: {today}", ""]

    tasks = store.open_tasks(include_one_on_ones=include)
    lines.append("## Your open tasks")
    for t in tasks:
        age = (_d(today) - _d(t["date"])).days if t["date"] else None
        lines.append(
            f"- {format_entry(t, link_projects=False)} — {_plural(age, 'day') if age is not None else 'undated'} ({_where(t)})"
        )
    if not tasks:
        lines.append("- none")
    if not include:
        hidden = len(store.open_tasks()) - len(tasks)
        if hidden:
            lines.append(f"- _{_plural(hidden, 'open task')} in 1:1 notebooks. Ask Claude (`open_tasks`) to see them._")
    lines.append("")

    owed = store.entries(
        "e.bullet = 'delegated' AND e.state = 'open'" + kind_filter, (), order="e.due IS NULL, e.due, p.date"
    )
    lines.append("## Owed to you")
    lines += [f"- {e['owner'] or '?'}: {e['text']}" + (f" (due {e['due']})" if e["due"] else "") for e in owed] or [
        "- none"
    ]
    lines.append("")

    decisions = store.entries("e.bullet = 'decision' AND p.date >= ?" + kind_filter, (since,))
    lines.append(f"## Decisions since {since}")
    lines += [f"- {e['text']} ({_where(e)})" for e in decisions] or ["- none"]
    lines.append("")

    window_start = (_d(today) - timedelta(days=int(cfg.raw["signals"]["window_days"]))).isoformat()
    signals = store.entries("e.signal = 1 AND p.date >= ?" + kind_filter, (window_start,))
    vectors = store.vectors([s["id"] for s in signals])
    by_id = {s["id"]: s for s in signals}
    groups = cluster(
        [(s["id"], vectors[s["id"]]) for s in signals if s["id"] in vectors], float(cfg.raw["signals"]["similarity"])
    )
    recurring = sorted((g for g in groups if len(g) >= 2), key=len, reverse=True)
    lines.append("## Recurring signals")
    for group in recurring:
        members = [by_id[i] for i in group]
        dates = ", ".join(sorted({m["date"] for m in members if m["date"]}))
        lines.append(f"- ({len(group)}×) {members[-1]['text']} — {dates}")
    if not recurring:
        lines.append("- none yet")
    lines.append("")

    week_ago = (_d(today) - timedelta(days=7)).isoformat()
    unclear = store.entries("e.confidence = 'low' AND p.date >= ?" + kind_filter, (week_ago,))
    lines.append("## Needs a look")
    lines += [f"- {format_entry(e, link_projects=False)} ({_where(e)})" for e in unclear] or ["- none"]
    return "\n".join(lines) + "\n"


def deliver(
    cfg, markdown: str, today: str, smtp_class=smtplib.SMTP_SSL, password_lookup=keychain_password
) -> list[str]:
    delivered = []
    outputs = cfg.digest_outputs
    if "wiki" in outputs or "morning" in outputs:
        out = cfg.wiki_dir / "journal"
        out.mkdir(parents=True, exist_ok=True)
        front = f"---\ntype: journal\ntags: [journal, digest]\ndate_updated: {today}\nstatus: active\n---\n\n"
        (out / "digest.md").write_text(front + markdown)
    for output in outputs:
        if output == "email":
            e = cfg.raw["digest"]["email"]
            msg = EmailMessage()
            msg["Subject"] = f"Journal digest {today}"
            msg["From"] = e["username"] or e["to"]
            msg["To"] = e["to"]
            msg.set_content(markdown)
            with smtp_class(e["smtp_host"], int(e["smtp_port"])) as smtp:
                smtp.login(
                    e["username"] or e["to"], password_lookup(e["password_keychain_service"], e["username"] or e["to"])
                )
                smtp.send_message(msg)
        delivered.append(output)
    return delivered
