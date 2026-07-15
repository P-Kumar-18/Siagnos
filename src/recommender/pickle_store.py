from pathlib import Path
import pickle

import numpy as np

from src.recommender.embedding_store import EmbeddingStore


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_EMBEDDING_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "embeddings.pkl"
)


class PickleEmbeddingStore(EmbeddingStore):

    def __init__(
        self,
        path: str | Path = DEFAULT_EMBEDDING_PATH,
    ):
        self.path = Path(path)

        if self.path.exists():
            self._load()
        else:
            self.model_name = None
            self.embedding_dimension = None

            self.fic_ids = np.array(
                [],
                dtype=np.int64,
            )

            self.embeddings = np.empty(
                (0, 0),
                dtype=np.float32,
            )

    def _load(self) -> None:
        with open(self.path, "rb") as file:
            data = pickle.load(file)

        self.model_name = data["model_name"]
        self.embedding_dimension = data["embedding_dimension"]

        self.fic_ids = data["fic_ids"]
        self.embeddings = data["embeddings"]

    def _save(self) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = {
            "model_name": self.model_name,
            "embedding_dimension": self.embedding_dimension,
            "fic_ids": self.fic_ids,
            "embeddings": self.embeddings,
        }

        with open(self.path, "wb") as file:
            pickle.dump(
                data,
                file,
            )

    def get_embedding(
        self,
        fic_id: int,
    ) -> np.ndarray:

        matches = np.where(self.fic_ids == fic_id)[0]

        if len(matches) == 0:
            raise KeyError(f"Embedding for fic_id={fic_id} does not exist.")

        return self.embeddings[matches[0]]

    def get_all_embeddings(
        self,
    ) -> tuple[np.ndarray, np.ndarray]:

        return (
            self.fic_ids,
            self.embeddings,
        )

    def save_embedding(
        self,
        fic_id: int,
        embedding: np.ndarray,
        model_name: str,
    ) -> None:

        embedding = np.asarray(
            embedding,
            dtype=np.float32,
        )

        if self.model_name is None:
            self.model_name = model_name
            self.embedding_dimension = len(
                embedding
            )

        if model_name != self.model_name:
            raise ValueError(
                f"Expected model "
                f"{self.model_name} "
                f"but received "
                f"{model_name}"
            )

        if len(embedding) != self.embedding_dimension:
            raise ValueError(f"Expected embedding dimension {self.embedding_dimension} but received {len(embedding)}")

        matches = np.where(self.fic_ids == fic_id)[0]

        if len(matches) > 0:
            self.embeddings[matches[0]] = embedding

        else:
            self.fic_ids = np.append(
                self.fic_ids,
                fic_id,
            )

            if len(self.embeddings) == 0:
                self.embeddings = embedding.reshape(
                    1,
                    -1,
                )

            else:
                self.embeddings = np.vstack(
                    [
                        self.embeddings,
                        embedding,
                    ]
                )

        self._save()

    def save_embeddings(
        self,
        fic_ids: np.ndarray,
        embeddings: np.ndarray,
        model_name: str,
    ) -> None:

        fic_ids = np.asarray(
            fic_ids,
            dtype=np.int64,
        )

        embeddings = np.asarray(
            embeddings,
            dtype=np.float32,
        )

        if len(fic_ids) != len(
            embeddings
        ):
            raise ValueError("Number of fic ids and embeddings do not match.")

        self.model_name = model_name
        self.embedding_dimension = (embeddings.shape[1])

        self.fic_ids = fic_ids
        self.embeddings = embeddings

        self._save()