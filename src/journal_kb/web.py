import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from journal_kb import queries
from journal_kb.pdf import render_page

PAGE_IMAGE = re.compile(r"^/page/(\d+)\.png$")

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Journal search</title>
<style>
  :root { --bg:#f4f5f2; --card:#fff; --ink:#1d1f21; --muted:#5b6166; --rule:#d5d8d2; --accent:#2e5a87; color-scheme: light dark; }
  @media (prefers-color-scheme: dark) { :root { --bg:#16181a; --card:#1f2225; --ink:#e6e7e3; --muted:#a9aeb2; --rule:#3a3f44; --accent:#8db4da; } }
  body { margin:0; padding:24px 16px; background:var(--bg); color:var(--ink); font:16px/1.5 -apple-system, system-ui, sans-serif; }
  main { max-width:860px; margin:0 auto; display:grid; gap:16px; }
  form { display:flex; gap:8px; flex-wrap:wrap; }
  input[type=search] { flex:1 1 280px; font:inherit; padding:10px 12px; border:1px solid var(--rule); border-radius:6px; background:var(--card); color:var(--ink); }
  input[type=date], button { font:inherit; padding:10px 12px; border:1px solid var(--rule); border-radius:6px; background:var(--card); color:var(--ink); }
  button { background:var(--accent); color:var(--bg); border-color:var(--accent); cursor:pointer; }
  .hit { display:grid; grid-template-columns:140px 1fr; gap:14px; background:var(--card); border:1px solid var(--rule); border-radius:6px; padding:12px; }
  .hit img { width:140px; border:1px solid var(--rule); background:#fff; }
  .meta { color:var(--muted); font-size:14px; }
  .text { font-size:17px; }
  @media (max-width:520px) { .hit { grid-template-columns:1fr; } .hit img { width:100%; } }
</style></head>
<body><main>
<h1>Journal search</h1>
<form id="f"><input type="search" id="q" name="q" placeholder="what did we decide about rate limiting?" autofocus>
<input type="date" id="since" name="since" aria-label="Since"><button>Search</button></form>
<div id="results"></div>
</main>
<script>
const SYMBOL = {task:"•", delegated:"→", event:"○", decision:"◇", question:"?", note:"–"};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
document.getElementById("f").addEventListener("submit", async ev => {
  ev.preventDefault();
  const p = new URLSearchParams({q: document.getElementById("q").value});
  const since = document.getElementById("since").value; if (since) p.set("since", since);
  const hits = await (await fetch("/api/search?" + p)).json();
  document.getElementById("results").innerHTML = hits.length ? hits.map(h => `
    <div class="hit"><a href="/page/${h.page_id}.png" target="_blank"><img loading="lazy" src="/page/${h.page_id}.png" alt="Journal page"></a>
    <div><div class="text">${h.signal ? "! " : ""}${SYMBOL[h.bullet]} ${h.owner && h.bullet === "delegated" ? esc(h.owner) + " " : ""}${esc(h.text)}</div>
    <div class="meta">${esc(h.date)} · ${esc(h.notebook)} p${h.page_no}${h.meeting ? " · " + esc(h.meeting) : ""}${h.project ? " · " + esc(h.project) : ""} · ${esc(h.state)}</div></div></div>`).join("")
    : "<p class='meta'>No matches.</p>";
});
</script></body></html>
"""


def make_server(cfg, store, embedder, port: int | None = None) -> HTTPServer:
    port = cfg.raw["web"]["port"] if port is None else port

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                return self._send(200, HTML.encode(), "text/html; charset=utf-8")
            if url.path == "/api/search":
                params = parse_qs(url.query)
                q = params.get("q", [""])[0].strip()
                hits = queries.search_notes(store, embedder, q, k=20, since=params.get("since", [None])[0]) if q else []
                return self._send(200, json.dumps(hits).encode(), "application/json")
            match = PAGE_IMAGE.match(url.path)
            if match:
                row = store.page(int(match.group(1)))
                if row:
                    return self._send(200, render_page(row["pdf_path"], row["page_no"], 100), "image/png")
            return self._send(404, b"not found", "text/plain")

        def log_message(self, *args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)
