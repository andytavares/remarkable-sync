def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def cluster(items: list[tuple[object, list[float]]], threshold: float) -> list[list[object]]:
    """Greedy single-pass clustering: each item joins the first cluster whose seed it resembles."""
    clusters: list[tuple[list[float], list[object]]] = []
    for key, vector in items:
        for seed, members in clusters:
            if _cosine(seed, vector) >= threshold:
                members.append(key)
                break
        else:
            clusters.append((vector, [key]))
    return [members for _, members in clusters]
