from abc import ABC, abstractmethod
import numpy as np


class EmbeddingStore(ABC):

    @abstractmethod
    def get_embedding(
        self,
        fic_id: int
    ) -> np.ndarray:
        """
        Return the embedding vector for a single fic.
        """
        pass


    @abstractmethod
    def get_all_embeddings(
        self,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Returns:
            fic_ids:
                Array of fic ids.

            embeddings:
                Matrix of embeddings.
        """
        pass


    @abstractmethod
    def save_embedding(
        self,
        fic_id: int,
        embedding: np.ndarray,
        model_name: str
    ) -> None:
        """
        Save or update one embedding.
        """
        pass


    @abstractmethod
    def save_embeddings(
        self,
        fic_ids: np.ndarray,
        embeddings: np.ndarray,
        model_name: str,
    ) -> None:
        """
        Save many embeddings at once.
        """
        pass