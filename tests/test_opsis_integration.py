from src.loader import get_connection
from src.recommender import PostgresEmbeddingStore, Recommender
from src.services import FicResolver, IngestionService


def test_database():
    print("\n=== 1. DATABASE CONNECTION ===")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fics;")
            fic_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM embeddings;")
            embedding_count = cur.fetchone()[0]

    print(f"Fics:       {fic_count}")
    print(f"Embeddings: {embedding_count}")
    print("PASS: Database connection works.")


def test_resolver(fic_id):
    print("\n=== 2. FIC RESOLUTION ===")

    fic = FicResolver({"fic_id": fic_id}).resolve()

    if "error" in fic:
        raise RuntimeError(f"Resolver failed: {fic['error']}")

    print(f"Resolved: {fic['name']}")
    print(f"Fandoms: {len(fic.get('fandom', []))}")
    print(f"Relationships: {len(fic.get('relationship', []))}")
    print(f"Freeform tags: {len(fic.get('freeform', []))}")

    required_metadata = (
        "warning",
        "category",
        "fandom",
        "relationship",
        "character",
        "freeform",
    )

    missing = [
        field
        for field in required_metadata
        if field not in fic
    ]

    if missing:
        raise RuntimeError(
            f"Metadata retrieval failed. Missing: {missing}"
        )

    print("PASS: FicResolver + metadata retrieval work.")

    return fic


def test_embedding(fic_id):
    print("\n=== 3. EMBEDDING STORAGE ===")

    store = PostgresEmbeddingStore()

    embedding = store.get_embedding(fic_id)

    if embedding is None:
        raise RuntimeError(
            f"No embedding found for fic {fic_id}."
        )

    print(f"Embedding dimensions: {len(embedding)}")

    if len(embedding) != 384:
        raise RuntimeError(
            f"Expected 384 dimensions, got {len(embedding)}."
        )

    print("PASS: PostgreSQL embedding retrieval works.")

    return store


def test_recommender(fic_id, store):
    print("\n=== 4. RECOMMENDER ===")

    with get_connection() as conn:
        recommender = Recommender(
            embedding_store=store,
            connection=conn,
        )

        recommendations = recommender.recommend(
            fic_id=fic_id
        )

    if not recommendations:
        raise RuntimeError(
            "Recommender returned no recommendations."
        )

    print(
        f"PASS: Recommender returned "
        f"{len(recommendations)} recommendations."
    )

    return recommendations


def test_batch_resolution(recommendations):
    print("\n=== 5. BATCH RECOMMENDATION RESOLUTION ===")

    recommendation_ids = [
        fic_id
        for fic_id, _ in recommendations
    ]

    resolved = FicResolver.resolve_many_from_ids(
        recommendation_ids
    )

    if len(resolved) != len(recommendation_ids):
        raise RuntimeError(
            "Batch resolution returned a different number "
            "of fics than expected."
        )

    resolved_ids = [
        fic["fic_id"]
        for fic in resolved
    ]

    if resolved_ids != recommendation_ids:
        raise RuntimeError(
            "Batch resolution did not preserve recommendation order."
        )

    print("PASS: Batch resolution works and preserves order.")

    print("\nRecommendations:")

    score_lookup = dict(recommendations)

    for index, fic in enumerate(resolved, start=1):
        score = score_lookup[fic["fic_id"]]

        print(
            f"{index:>2}. "
            f"{fic['name']} "
            f"({score * 100:.1f}%)"
        )


def test_existing_fic(fic_id):
    print("\n")
    print("=" * 60)
    print("TESTING EXISTING FIC PIPELINE")
    print("=" * 60)

    fic = test_resolver(fic_id)
    store = test_embedding(fic["fic_id"])
    recommendations = test_recommender(
        fic["fic_id"],
        store,
    )
    test_batch_resolution(recommendations)


def test_new_fic(url):
    print("\n")
    print("=" * 60)
    print("TESTING ON-DEMAND INGESTION")
    print("=" * 60)

    payload = {"url": url}

    source = FicResolver(payload).resolve()

    if "error" not in source:
        print(
            "WARNING: This fic is already in the database. "
            "Choose another URL to test ingestion."
        )
        return

    print("Fic not found. Starting ingestion...")

    result = IngestionService(payload).ingest()

    if "error" in result:
        raise RuntimeError(
            f"Ingestion failed: {result['error']}"
        )

    print("Ingestion completed.")

    source = FicResolver(payload).resolve()

    if "error" in source:
        raise RuntimeError(
            "Ingestion completed, but the fic could not "
            "be resolved afterward."
        )

    print(f"Resolved newly ingested fic: {source['name']}")

    store = test_embedding(source["fic_id"])

    recommendations = test_recommender(
        source["fic_id"],
        store,
    )

    test_batch_resolution(recommendations)

    print("\nPASS: Full on-demand ingestion pipeline works.")


if __name__ == "__main__":
    # --------------------------------------------------
    # REQUIRED:
    # Replace this with a fic ID already in your DB.
    # --------------------------------------------------

    EXISTING_FIC_ID = 22080895

    # --------------------------------------------------
    # OPTIONAL:
    # Replace this with a REAL AO3 work URL that is
    # definitely not already in your database.
    #
    # Leave as None for the first test.
    # --------------------------------------------------

    NEW_FIC_URL = "https://archiveofourown.org/works/81859246/chapters/215350696"

    try:
        test_database()

        if EXISTING_FIC_ID == 0:
            print(
                "\nSet EXISTING_FIC_ID before continuing."
            )
        else:
            test_existing_fic(EXISTING_FIC_ID)

        if NEW_FIC_URL:
            test_new_fic(NEW_FIC_URL)

        print("\n")
        print("=" * 60)
        print("ALL ENABLED TESTS PASSED")
        print("=" * 60)

    except Exception as exc:
        print("\n")
        print("=" * 60)
        print("TEST FAILED")
        print("=" * 60)
        print(f"{type(exc).__name__}: {exc}")

        raise