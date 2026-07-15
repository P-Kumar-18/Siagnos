import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def compute_cosine_similarity(
    query_embedding: np.ndarray,
    candidate_embeddings: np.ndarray,
) -> np.ndarray:

    similarities = cosine_similarity(
        query_embedding.reshape(1, -1),
        candidate_embeddings,
    )[0]

    return similarities


def compute_jaccard_similarity(
    values_a: set[str],
    values_b: set[str],
) -> float:

    if not values_a and not values_b:
        return 1.0

    union = values_a | values_b

    if not union:
        return 0.0

    intersection = values_a & values_b

    return len(intersection) / len(union)


def min_max_normalize(
    value: float,
    minimum: float,
    maximum: float,
) -> float:

    if maximum == minimum:
        return 0.0

    return (value - minimum) / (maximum - minimum)