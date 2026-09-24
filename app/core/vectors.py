"""ChromaDB access (vectors only; texts live in SQLite)."""

from functools import lru_cache

from app.config import get_settings

COLLECTION_NAMES = ("ayah_ar", "ayah_en", "hadith_ar", "hadith_en", "dorar_ar")
# Core books indexed in DEMO_SUBSET mode. Lexical (FTS5) search always covers every collection.
DEMO_HADITH_COLLECTIONS = ["bukhari", "muslim", "nawawi", "qudsi", "dehlawi"]


@lru_cache
def client():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    s = get_settings()
    path = s.resolve(s.chroma_path)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))


def get_collection(name: str):
    return client().get_or_create_collection(name, metadata={"hnsw:space": "cosine"}, embedding_function=None)


def index_counts() -> dict[str, int]:
    try:
        return {n: get_collection(n).count() for n in COLLECTION_NAMES}
    except Exception:  # noqa: BLE001 - index optional
        return {}


def query(name: str, vec: list[float], k: int = 50) -> list[tuple[int, float]]:
    """[(sqlite_id, cosine_similarity)] best first. Empty if the collection is missing/empty."""
    return [(int(i), sim) for i, sim in query_raw(name, vec, k)]


def query_raw(name: str, vec: list[float], k: int = 50) -> list[tuple[str, float]]:
    col = get_collection(name)
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[vec], n_results=min(k, col.count()), include=["distances"])
    return [(i, 1.0 - d) for i, d in zip(res["ids"][0], res["distances"][0], strict=True)]
