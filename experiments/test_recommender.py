from src.loader.database import get_connection
from src.recommender.pickle_store import PickleEmbeddingStore
from src.recommender.recommend import Recommender


def main():

    connection = get_connection()

    store = PickleEmbeddingStore()

    recommender = Recommender(
        embedding_store=store,
        connection=connection,
    )

    fic_id = int(input("Enter fic id: "))

    recommendations = (
        recommender.recommend(
            fic_id=fic_id,
            top_k=10,
            retrieval_size=100,
        )
    )

    print()
    print("Recommendations")
    print("-" * 50)

    for rank, (recommended_fic_id, score) in enumerate(
        recommendations,
        start=1,
    ):
        print(
            f"{rank:2d}. "
            f"{recommended_fic_id} "
            f"({score:.4f})"
        )

    connection.close()


if __name__ == "__main__":
    main()