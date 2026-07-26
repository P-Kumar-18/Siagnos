from src.recommender import compute_jaccard_similarity


# Global weight constants for weighted hybrid recommendation scoring
EMBEDDING_WEIGHT = 0.70
FANDOM_WEIGHT = 0.15
RELATIONSHIP_WEIGHT = 0.10
POPULARITY_WEIGHT = 0.05


def compute_popularity_score(kudos_score: float, bookmark_score: float) -> float:
    """Calculate normalized popularity score combining kudos and bookmark metrics."""
    return (kudos_score + bookmark_score) / 2.0


def compute_final_score(
    embedding_similarity: float,
    query_fandoms: set[str],
    candidate_fandoms: set[str],
    query_relationships: set[str],
    candidate_relationships: set[str],
    normalized_kudos: float,
    normalized_bookmarks: float,
) -> float:
    """Compute weighted hybrid recommendation score from embedding, fandom, relationship, and popularity metrics."""
    fandom_score = compute_jaccard_similarity(query_fandoms, candidate_fandoms)
    relationship_score = compute_jaccard_similarity(query_relationships, candidate_relationships)
    popularity_score = compute_popularity_score(normalized_kudos, normalized_bookmarks)

    final_score = (
        EMBEDDING_WEIGHT * embedding_similarity
        + FANDOM_WEIGHT * fandom_score
        + RELATIONSHIP_WEIGHT * relationship_score
        + POPULARITY_WEIGHT * popularity_score
    )

    return final_score