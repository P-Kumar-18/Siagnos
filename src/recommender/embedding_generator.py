from sentence_transformers import SentenceTransformer
import numpy as np

from src.recommender.embedding_store import EmbeddingStore


class EmbeddingGenerator:

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def generate_embeddings(
        self,
        summaries: list[str],
    ) -> np.ndarray:

        embeddings = self.model.encode(
            summaries,
            convert_to_numpy=True,
            show_progress_bar=True,
        )

        return embeddings.astype(
            np.float32
        )

    def generate_and_store(
        self,
        fic_ids: np.ndarray,
        summaries: list[str],
        store: EmbeddingStore,
    ) -> None:

        embeddings = self.generate_embeddings(summaries)

        store.save_embeddings(
            fic_ids=fic_ids,
            embeddings=embeddings,
            model_name=self.model_name,
        )