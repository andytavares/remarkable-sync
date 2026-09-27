import httpx


class OllamaEmbedder:
    """Embeddings from a local Ollama server. nomic-embed-text expects task prefixes on its inputs."""

    def __init__(self, url: str, model: str, dimensions: int, document_prefix: str = "", query_prefix: str = ""):
        self.url = url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix

    def _embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(f"{self.url}/api/embed", json={"model": self.model, "input": texts}, timeout=120)
        response.raise_for_status()
        return response.json()["embeddings"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self.document_prefix + t for t in texts]) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.query_prefix + text])[0]


def make_embedder(cfg) -> OllamaEmbedder:
    e = cfg.raw["embed"]
    return OllamaEmbedder(e["ollama_url"], e["model"], int(e["dimensions"]), e["document_prefix"], e["query_prefix"])
