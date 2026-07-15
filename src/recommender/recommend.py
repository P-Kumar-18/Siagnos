import numpy as np

from src.recommender.similarity import compute_cosine_similarity, min_max_normalize

from src.recommender.ranker import compute_final_score


class Recommender:

    def __init__(
        self,
        embedding_store,
        connection,
    ):
        self.embedding_store = embedding_store
        self.connection = connection

    def _get_max_popularity(
        self,
    ) -> tuple[int, int]:

        query = """
        SELECT
            MAX(kudos),
            MAX(bookmarks)
        FROM fics
        """

        with self.connection.cursor() as cur:
            cur.execute(query)

            return cur.fetchone()

    def _get_batch_metadata(
        self,
        fic_ids: list[int],
    ) -> dict[int, dict]:

        metadata = {
            fic_id: {
                "fandoms": set(),
                "relationships": set(),
                "kudos": 0,
                "bookmarks": 0,
            }
            for fic_id in fic_ids
        }

        # ----------------------------
        # Popularity
        # ----------------------------

        popularity_query = """
        SELECT
            fic_id,
            kudos,
            bookmarks
        FROM fics
        WHERE fic_id = ANY(%s)
        """

        with self.connection.cursor() as cur:

            cur.execute(
                popularity_query,
                (fic_ids,)
            )

            for fic_id, kudos, bookmarks in cur.fetchall():

                metadata[fic_id]["kudos"] = (kudos or 0)

                metadata[fic_id]["bookmarks"] = (bookmarks or 0)

        # ----------------------------
        # Fandoms
        # ----------------------------

        fandom_query = """
        SELECT
            fj.fic_id,
            fv.fandom
        FROM fandom_join fj
        JOIN fandom_value fv
            ON fj.fandom_id = fv.fandom_id
        WHERE fj.fic_id = ANY(%s)
        """

        with self.connection.cursor() as cur:

            cur.execute(
                fandom_query,
                (fic_ids,)
            )

            for fic_id, fandom in cur.fetchall():

                metadata[fic_id]["fandoms"].add(fandom)

        # ----------------------------
        # Relationships
        # ----------------------------

        relationship_query = """
        SELECT
            rj.fic_id,
            rv.relationship
        FROM relationship_join rj
        JOIN relationship_value rv
            ON rj.relationship_id = rv.relationship_id
        WHERE rj.fic_id = ANY(%s)
        """

        with self.connection.cursor() as cur:

            cur.execute(
                relationship_query,
                (fic_ids,)
            )

            for fic_id, relationship in cur.fetchall():

                metadata[fic_id]["relationships"].add(relationship)

        return metadata

    def recommend(
        self,
        fic_id: int,
        top_k: int = 10,
        retrieval_size: int = 100,
    ) -> list[tuple[int, float]]:

        query_embedding = (self.embedding_store.get_embedding(fic_id))

        candidate_ids, candidate_embeddings = (self.embedding_store.get_all_embeddings())

        similarities = (
            compute_cosine_similarity(
                query_embedding,
                candidate_embeddings,
            )
        )

        sorted_indices = np.argsort(similarities)[::-1]

        # ---------------------------------
        # Retrieval Stage
        # ---------------------------------

        retrieved_candidate_ids = []

        for index in sorted_indices:

            candidate_id = int(candidate_ids[index])

            if candidate_id == fic_id:
                continue

            retrieved_candidate_ids.append(candidate_id)

            if len(retrieved_candidate_ids) >= retrieval_size:
                break

        # ---------------------------------
        # Metadata Stage
        # ---------------------------------

        metadata = (self._get_batch_metadata([fic_id] + retrieved_candidate_ids))

        query_metadata = metadata[fic_id]

        max_kudos, max_bookmarks = (self._get_max_popularity())

        # ---------------------------------
        # Ranking Stage
        # ---------------------------------

        recommendations = []

        similarity_lookup = {
            int(candidate_ids[index]): similarities[index] for index in sorted_indices
        }

        for candidate_id in (retrieved_candidate_ids):

            candidate_metadata = (metadata[candidate_id])

            normalized_kudos = (
                min_max_normalize(
                    candidate_metadata["kudos"],
                    0,
                    max_kudos,
                )
            )

            normalized_bookmarks = (
                min_max_normalize(
                    candidate_metadata["bookmarks"],
                    0,
                    max_bookmarks,
                )
            )

            score = (
                compute_final_score(
                    embedding_similarity = similarity_lookup[candidate_id],
                    query_fandoms = query_metadata["fandoms"],
                    candidate_fandoms = candidate_metadata["fandoms"],
                    query_relationships = query_metadata["relationships"],
                    candidate_relationships = candidate_metadata["relationships"],
                    normalized_kudos = normalized_kudos,
                    normalized_bookmarks = normalized_bookmarks,
                )
            )

            recommendations.append(
                (
                    candidate_id,
                    score,
                )
            )

        recommendations.sort(
            key=lambda x: x[1],
            reverse=True,
        )

        return recommendations[:top_k]