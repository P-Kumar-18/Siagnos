from src.loader.database import get_connection
from src.recommender.embedding_generator import EmbeddingGenerator
from src.recommender.pickle_store import PickleEmbeddingStore


def main():

    connection = get_connection()

    query = """
    SELECT
        fic_id,
        summary
    FROM fics
    WHERE summary IS NOT NULL
    ORDER BY fic_id
    """

    with connection.cursor() as cur:
        cur.execute(query)

        rows = cur.fetchall()

    fic_ids = [row[0] for row in rows]

    summaries = [row[1] for row in rows]

    generator = EmbeddingGenerator()

    store = PickleEmbeddingStore()

    generator.generate_and_store(
        fic_ids=fic_ids,
        summaries=summaries,
        store=store,
    )

    print(
        f"Generated embeddings for "
        f"{len(fic_ids)} fics."
    )

    connection.close()


if __name__ == "__main__":
    main()