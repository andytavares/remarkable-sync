import json

FIELDS = (
    "id",
    "page_id",
    "bullet",
    "state",
    "text",
    "owner",
    "due",
    "project",
    "meeting",
    "date",
    "notebook",
    "page_no",
)


def _slim(row: dict) -> dict:
    out = {k: row[k] for k in FIELDS}
    out["signal"] = bool(row["signal"])
    out["priority"] = bool(row["priority"])
    if "distance" in row:
        out["distance"] = round(row["distance"], 4)
    return out


def search_notes(store, embedder, query: str, k: int = 8, since: str | None = None) -> list[dict]:
    return [_slim(r) for r in store.search(embedder.embed_query(query), k=k, since=since)]


def open_tasks(store, owner: str | None = None) -> list[dict]:
    return [_slim(r) for r in store.open_tasks(owner=owner)]


def decisions(store, project: str | None = None, since: str | None = None) -> list[dict]:
    where, params = "e.bullet = 'decision'", []
    if project:
        where += " AND e.project = ?"
        params.append(project)
    if since:
        where += " AND p.date >= ?"
        params.append(since)
    return [_slim(r) for r in store.entries(where, tuple(params))]


def signals(store, since: str | None = None) -> list[dict]:
    where, params = "e.signal = 1", ()
    if since:
        where, params = where + " AND p.date >= ?", (since,)
    return [_slim(r) for r in store.entries(where, params)]


def page(store, page_id: int) -> dict | None:
    row = store.page(page_id)
    if not row:
        return None
    return {
        "id": row["id"],
        "notebook": row["notebook"],
        "page_no": row["page_no"],
        "date": row["date"],
        "events": json.loads(row["events_json"]),
        "transcription": row["transcription"],
        "pdf": f"{row['pdf_path']}#page={row['page_no']}",
    }
