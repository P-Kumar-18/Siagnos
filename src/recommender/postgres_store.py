from src.loader import get_connection
from src.recommender import EmbeddingStore

import numpy as np
import pickle


class PostgresEmbeddingStore(EmbeddingStore):
    """PostgreSQL-backed storage implementation for vector embeddings using bytea payload storage."""

    _cached_fic_ids: np.ndarray | None = None
    _cached_embeddings: np.ndarray | None = None

    def _get_store_metadata(self, connection) -> tuple[str, int] | None:
        """Fetch model metadata from existing embeddings in the database."""
        query = """
        SELECT
            model_name,
            embedding_dimension
        FROM embeddings
        LIMIT 1
        """

        with connection.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()

        if row is None:
            return None

        return row[0], row[1]

    def _validate_embedding(self, connection, embedding: np.ndarray, model_name: str) -> np.ndarray:
        """Validate embedding dimensions and model compatibility against stored metadata."""
        embedding = np.asarray(embedding, dtype=np.float32)

        if embedding.ndim != 1:
            raise ValueError("Embedding must be a one-dimensional array.")

        metadata = self._get_store_metadata(connection)

        if metadata is None:
            return embedding

        stored_model_name, stored_dimension = metadata

        if model_name != stored_model_name:
            raise ValueError(f"Expected model {stored_model_name} but received {model_name}")

        if len(embedding) != stored_dimension:
            raise ValueError(f"Expected embedding dimension {stored_dimension} but received {len(embedding)}")

        return embedding

    def get_embedding(self, fic_id: int) -> np.ndarray:
        """Retrieve and deserialize vector embedding for a single fic ID."""
        query = "SELECT payload FROM embeddings WHERE fic_id = %s"

        with get_connection() as connection:
            with connection.cursor() as cur:
                cur.execute(query, (fic_id,))
                row = cur.fetchone()

        if row is None:
            raise KeyError(f"Embedding for fic_id={fic_id} does not exist.")

        embedding = pickle.loads(bytes(row[0]))

        return np.asarray(embedding, dtype=np.float32)

    def get_all_embeddings(self) -> tuple[np.ndarray, np.ndarray]:
        """Retrieve all stored fic IDs and vector embeddings matrix from database."""

        if self.__class__._cached_fic_ids is not None and self.__class__._cached_embeddings is not None:
            return self.__class__._cached_fic_ids, self.__class__._cached_embeddings
        
        query = """
        SELECT
            fic_id,
            payload
        FROM embeddings
        ORDER BY fic_id
        """

        with get_connection() as connection:
            with connection.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()

        if not rows:
            return np.array([], dtype=np.int64), np.empty((0, 0), dtype=np.float32)

        fic_ids = np.array([row[0] for row in rows], dtype=np.int64)
        embeddings = np.stack([np.asarray(pickle.loads(bytes(row[1])), dtype=np.float32) for row in rows])

        self.__class__._cached_fic_ids = fic_ids
        self.__class__._cached_embeddings = embeddings

        return fic_ids, embeddings
    
    @classmethod
    def _invalidate_cache(cls) -> None:
        """Invalidate the in-memory embedding cache after database writes."""
        cls._cached_fic_ids = None
        cls._cached_embeddings = None

    def save_embedding(self, fic_id: int, embedding: np.ndarray, model_name: str) -> None:
        """Upsert a single fic embedding vector into PostgreSQL database."""
        query = """
        INSERT INTO embeddings (
            fic_id,
            model_name,
            embedding_dimension,
            payload
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fic_id)
        DO UPDATE SET
            model_name = EXCLUDED.model_name,
            embedding_dimension = EXCLUDED.embedding_dimension,
            payload = EXCLUDED.payload
        """

        with get_connection() as connection:
            embedding = self._validate_embedding(connection, embedding, model_name)
            payload = pickle.dumps(embedding, protocol=pickle.HIGHEST_PROTOCOL)

            with connection.cursor() as cur:
                cur.execute(
                    query,
                    (
                        int(fic_id),
                        model_name,
                        len(embedding),
                        payload,
                    ),
                )

            connection.commit()
        
        self._invalidate_cache()

    def save_embeddings(self, fic_ids: np.ndarray, embeddings: np.ndarray, model_name: str) -> None:
        """Batch upsert multiple fic embedding vectors into PostgreSQL database."""
        fic_ids = np.asarray(fic_ids, dtype=np.int64)
        embeddings = np.asarray(embeddings, dtype=np.float32)

        if fic_ids.ndim != 1:
            raise ValueError("Fic IDs must be a one-dimensional array.")

        if embeddings.ndim != 2:
            raise ValueError("Embeddings must be a two-dimensional array.")

        if len(fic_ids) != len(embeddings):
            raise ValueError("Number of fic ids and embeddings do not match.")

        if len(fic_ids) == 0:
            return

        query = """
        INSERT INTO embeddings (
            fic_id,
            model_name,
            embedding_dimension,
            payload
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fic_id)
        DO UPDATE SET
            model_name = EXCLUDED.model_name,
            embedding_dimension = EXCLUDED.embedding_dimension,
            payload = EXCLUDED.payload
        """

        embedding_dimension = embeddings.shape[1]

        with get_connection() as connection:
            metadata = self._get_store_metadata(connection)

            if metadata is not None:
                stored_model_name, stored_dimension = metadata

                if model_name != stored_model_name:
                    raise ValueError(f"Expected model {stored_model_name} but received {model_name}")

                if embedding_dimension != stored_dimension:
                    raise ValueError(
                        f"Expected embedding dimension {stored_dimension} but received {embedding_dimension}"
                    )

            rows = [
                (
                    int(fic_id),
                    model_name,
                    embedding_dimension,
                    pickle.dumps(embedding, protocol=pickle.HIGHEST_PROTOCOL),
                )
                for fic_id, embedding in zip(fic_ids, embeddings)
            ]

            with connection.cursor() as cur:
                cur.executemany(query, rows)

            connection.commit()