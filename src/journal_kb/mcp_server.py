from mcp.server import MCPServer

from journal_kb import queries


def build_server(cfg, store, embedder) -> MCPServer:
    mcp = MCPServer("journal-kb")

    @mcp.tool()
    def search_notes(query: str, k: int = 8, since: str | None = None) -> list[dict]:
        """Semantic search over every bullet in the reMarkable journal, 1:1 notebooks included.
        since is an optional YYYY-MM-DD lower bound on the page date. Each hit carries page_id for `page`."""
        return queries.search_notes(store, embedder, query, k=k, since=since)

    @mcp.tool()
    def open_tasks(owner: str | None = None) -> list[dict]:
        """Open tasks. Without owner: tasks the writer owns (•). With owner initials (e.g. "JM"): tasks delegated to them (→)."""
        return queries.open_tasks(store, owner=owner)

    @mcp.tool()
    def decisions(project: str | None = None, since: str | None = None) -> list[dict]:
        """Decisions (△), optionally for one project slug and/or since a YYYY-MM-DD date."""
        return queries.decisions(store, project=project, since=since)

    @mcp.tool()
    def signals(since: str | None = None) -> list[dict]:
        """Architecture and vision signals (!), optionally since a YYYY-MM-DD date."""
        return queries.signals(store, since=since)

    @mcp.tool()
    def page(page_id: int) -> dict | None:
        """The full transcription, events, and source PDF location of one journal page."""
        return queries.page(store, page_id)

    return mcp
