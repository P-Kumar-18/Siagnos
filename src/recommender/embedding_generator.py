from src.recommender import EmbeddingStore

import numpy as np


class EmbeddingGenerator:
    """Handles the initialization and generation of text embeddings."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):

        # Import locally to avoid loading heavy modules if the class is just imported but not instantiated
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name

        # Initialize and store the model instance on the object
        self.model = SentenceTransformer(model_name)

    def generate_embeddings(self, summaries: list[str]) -> np.ndarray:

        # Generate embeddings directly to numpy arrays with a progress bar
        embeddings = self.model.encode(summaries, convert_to_numpy=True, show_progress_bar=True)
        
        # Ensure consistent 32-bit float typing for downstream storage
        return embeddings.astype(np.float32)

    def generate_and_store(self, fic_ids: np.ndarray, summaries: list[str], store: EmbeddingStore) -> None:
        # Generate the raw embeddings from the provided summaries
        embeddings = self.generate_embeddings(summaries)

        # Persist the generated embeddings mapped to their respective IDs
        store.save_embeddings(fic_ids=fic_ids, embeddings=embeddings, model_name=self.model_name)