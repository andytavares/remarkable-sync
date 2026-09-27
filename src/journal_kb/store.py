import sqlite3
from pathlib import Path

import sqlite_vec

from journal_kb.models import PageRead

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  path TEXT PRIMARY KEY,
  mtime REAL NOT NULL,
  processed_at TEXT
);
CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY,
  notebook TEXT NOT NULL,
  kind TEXT NOT NULL,
  page_no INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  pdf_path TEXT NOT NULL,
  date TEXT,
  transcription TEXT NOT NULL,
  events_json TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  UNIQUE (notebook, page_no)
);
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  bullet TEXT NOT NULL,
  signal INTEGER NOT NULL,
  priority INTEGER NOT NULL,
  state TEXT NOT NULL,
  text TEXT NOT NULL,
  owner TEXT,
  due TEXT,
  project TEXT,
  meeting TEXT,
  confidence TEXT NOT NULL,
  embedded INTEGER NOT NULL DEFAULT 0
);
"""

ENTRY_COLUMNS = """
  e.id, e.page_id, e.seq, e.bullet, e.signal, e.priority, e.state, e.text, e.owner, e.due,
  e.project, e.meeting, e.confidence, p.date, p.notebook, p.kind, p.page_no, p.pdf_path
"""


class Store:
    def __init__(self, path: Path, dimensions: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0("
            f"entry_id INTEGER PRIMARY KEY, embedding float[{dimensions}], kind TEXT, date TEXT)"
        )
        self.db.commit()

    # snapshots
    def snapshot_done(self, path: str, mtime: float) -> bool:
        row = self.db.execute("SELECT mtime FROM snapshots WHERE path = ?", (path,)).fetchone()
        return row is not None and row["mtime"] == mtime

    def mark_snapshot(self, path: str, mtime: float, processed_at: str) -> None:
        self.db.execute(
            "INSERT INTO snapshots(path, mtime, processed_at) VALUES (?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET mtime = excluded.mtime, processed_at = excluded.processed_at",
            (path, mtime, processed_at),
        )
        self.db.commit()

    # pages
    def page_hash(self, notebook: str, page_no: int) -> str | None:
        row = self.db.execute(
            "SELECT sha256 FROM pages WHERE notebook = ? AND page_no = ?", (notebook, page_no)
        ).fetchone()
        return row["sha256"] if row else None

    def page_date(self, notebook: str, page_no: int) -> str | None:
        row = self.db.execute(
            "SELECT date FROM pages WHERE notebook = ? AND page_no = ?", (notebook, page_no)
        ).fetchone()
        return row["date"] if row else None

    def upsert_page(
        self,
        *,
        notebook: str,
        kind: str,
        page_no: int,
        sha256: str,
        pdf_path: str,
        date: str | None,
        read: PageRead,
        input_tokens: int,
        output_tokens: int,
    ) -> int:
        existing = self.db.execute(
            "SELECT id FROM pages WHERE notebook = ? AND page_no = ?", (notebook, page_no)
        ).fetchone()
        if existing:
            self._delete_page(existing["id"])
        events_json = "[" + ",".join(e.model_dump_json() for e in read.events) + "]"
        cur = self.db.execute(
            "INSERT INTO pages(notebook, kind, page_no, sha256, pdf_path, date, transcription, events_json, "
            "input_tokens, output_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                notebook,
                kind,
                page_no,
                sha256,
                pdf_path,
                date,
                read.transcription,
                events_json,
                input_tokens,
                output_tokens,
            ),
        )
        page_id = cur.lastrowid
        self.db.executemany(
            "INSERT INTO entries(page_id, seq, bullet, signal, priority, state, text, owner, due, project, meeting, "
            "confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    page_id,
                    seq,
                    e.bullet,
                    int(e.signal),
                    int(e.priority),
                    e.state,
                    e.text,
                    e.owner,
                    e.due,
                    e.project,
                    e.meeting,
                    e.confidence,
                )
                for seq, e in enumerate(read.entries)
            ],
        )
        self.db.commit()
        return page_id

    def _delete_page(self, page_id: int) -> None:
        self.db.execute(
            "DELETE FROM vec_entries WHERE entry_id IN (SELECT id FROM entries WHERE page_id = ?)", (page_id,)
        )
        self.db.execute("DELETE FROM pages WHERE id = ?", (page_id,))

    def delete_pages_after(self, notebook: str, page_count: int) -> int:
        rows = self.db.execute(
            "SELECT id FROM pages WHERE notebook = ? AND page_no > ?", (notebook, page_count)
        ).fetchall()
        for row in rows:
            self._delete_page(row["id"])
        self.db.commit()
        return len(rows)

    def page(self, page_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        return dict(row) if row else None

    def pages(self, kinds: tuple[str, ...]) -> list[dict]:
        marks = ",".join("?" * len(kinds))
        rows = self.db.execute(
            f"SELECT * FROM pages WHERE kind IN ({marks}) ORDER BY date, notebook, page_no", kinds
        ).fetchall()
        return [dict(r) for r in rows]

    # entries
    def entries(
        self, where: str = "1", params: tuple = (), order: str = "p.date, p.notebook, p.page_no, e.seq"
    ) -> list[dict]:
        rows = self.db.execute(
            f"SELECT {ENTRY_COLUMNS} FROM entries e JOIN pages p ON p.id = e.page_id WHERE {where} ORDER BY {order}",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def open_tasks(self, owner: str | None = None, include_one_on_ones: bool = True) -> list[dict]:
        where = "e.state = 'open' AND " + ("e.bullet = 'delegated' AND e.owner = ?" if owner else "e.bullet = 'task'")
        params: tuple = (owner,) if owner else ()
        if not include_one_on_ones:
            where += " AND p.kind != 'one_on_one'"
        return self.entries(where, params)

    def unembedded(self) -> list[dict]:
        # Meeting headings are not embedded: each bullet under them carries the meeting title instead.
        return self.entries("e.embedded = 0 AND e.bullet != 'event'")

    def set_vectors(self, vectors: list[tuple[dict, list[float]]]) -> None:
        for entry, vector in vectors:
            self.db.execute(
                "INSERT INTO vec_entries(entry_id, embedding, kind, date) VALUES (?, ?, ?, ?)",
                (entry["id"], sqlite_vec.serialize_float32(vector), entry["kind"], entry["date"] or ""),
            )
            self.db.execute("UPDATE entries SET embedded = 1 WHERE id = ?", (entry["id"],))
        self.db.commit()

    def vectors(self, entry_ids: list[int]) -> dict[int, list[float]]:
        out = {}
        for entry_id in entry_ids:
            row = self.db.execute(
                "SELECT vec_to_json(embedding) AS v FROM vec_entries WHERE entry_id = ?", (entry_id,)
            ).fetchone()
            if row:
                out[entry_id] = [float(x) for x in row["v"].strip("[]").split(",")]
        return out

    def search(
        self, query_vector: list[float], k: int = 8, since: str | None = None, include_one_on_ones: bool = True
    ) -> list[dict]:
        where = ["embedding MATCH ?", "k = ?"]
        params: list = [sqlite_vec.serialize_float32(query_vector), k]
        if since:
            where.append("date >= ?")
            params.append(since)
        if not include_one_on_ones:
            where.append("kind != 'one_on_one'")
        hits = self.db.execute(
            f"SELECT entry_id, distance FROM vec_entries WHERE {' AND '.join(where)} ORDER BY distance", params
        ).fetchall()
        by_id = (
            {
                e["id"]: e
                for e in self.entries(f"e.id IN ({','.join('?' * len(hits))})", tuple(h["entry_id"] for h in hits))
            }
            if hits
            else {}
        )
        return [{**by_id[h["entry_id"]], "distance": h["distance"]} for h in hits if h["entry_id"] in by_id]

    def usage(self) -> dict:
        row = self.db.execute(
            "SELECT COUNT(*) AS pages, COALESCE(SUM(input_tokens), 0) AS input_tokens, "
            "COALESCE(SUM(output_tokens), 0) AS output_tokens FROM pages"
        ).fetchone()
        return dict(row)
