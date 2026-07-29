def populate_metadata(cur, fic: dict) -> dict:
    """Populate a fic dictionary with metadata from all join tables."""

    fic_id = fic["fic_id"]

    cur.execute(
        """
        SELECT
            ARRAY(
                SELECT v.warning
                FROM warning_join j
                JOIN warning_value v ON j.warning_id = v.warning_id
                WHERE j.fic_id = %s
                ORDER BY v.warning
            ) AS warning,

            ARRAY(
                SELECT v.categories
                FROM categories_join j
                JOIN categories_value v ON j.categories_id = v.categories_id
                WHERE j.fic_id = %s
                ORDER BY v.categories
            ) AS category,

            ARRAY(
                SELECT v.fandom
                FROM fandom_join j
                JOIN fandom_value v ON j.fandom_id = v.fandom_id
                WHERE j.fic_id = %s
                ORDER BY v.fandom
            ) AS fandom,

            ARRAY(
                SELECT v.relationship
                FROM relationship_join j
                JOIN relationship_value v
                    ON j.relationship_id = v.relationship_id
                WHERE j.fic_id = %s
                ORDER BY v.relationship
            ) AS relationship,

            ARRAY(
                SELECT v.characters
                FROM characters_join j
                JOIN characters_value v ON j.characters_id = v.characters_id
                WHERE j.fic_id = %s
                ORDER BY v.characters
            ) AS character,

            ARRAY(
                SELECT v.freeform
                FROM freeform_join j
                JOIN freeform_value v ON j.freeform_id = v.freeform_id
                WHERE j.fic_id = %s
                ORDER BY v.freeform
            ) AS freeform
        """,
        (fic_id,) * 6,
    )

    row = cur.fetchone()

    metadata_fields = (
        "warning",
        "category",
        "fandom",
        "relationship",
        "character",
        "freeform",
    )

    fic.update(dict(zip(metadata_fields, row)))

    return fic


def populate_metadata_many(cur, fics: list[dict]) -> list[dict]:
    """Populate metadata for multiple fic dictionaries in a single query."""

    if not fics:
        return fics

    fic_ids = [fic["fic_id"] for fic in fics]

    cur.execute(
        """
        SELECT
            f.fic_id,

            ARRAY(
                SELECT v.warning
                FROM warning_join j
                JOIN warning_value v ON j.warning_id = v.warning_id
                WHERE j.fic_id = f.fic_id
                ORDER BY v.warning
            ) AS warning,

            ARRAY(
                SELECT v.categories
                FROM categories_join j
                JOIN categories_value v ON j.categories_id = v.categories_id
                WHERE j.fic_id = f.fic_id
                ORDER BY v.categories
            ) AS category,

            ARRAY(
                SELECT v.fandom
                FROM fandom_join j
                JOIN fandom_value v ON j.fandom_id = v.fandom_id
                WHERE j.fic_id = f.fic_id
                ORDER BY v.fandom
            ) AS fandom,

            ARRAY(
                SELECT v.relationship
                FROM relationship_join j
                JOIN relationship_value v
                    ON j.relationship_id = v.relationship_id
                WHERE j.fic_id = f.fic_id
                ORDER BY v.relationship
            ) AS relationship,

            ARRAY(
                SELECT v.characters
                FROM characters_join j
                JOIN characters_value v ON j.characters_id = v.characters_id
                WHERE j.fic_id = f.fic_id
                ORDER BY v.characters
            ) AS character,

            ARRAY(
                SELECT v.freeform
                FROM freeform_join j
                JOIN freeform_value v ON j.freeform_id = v.freeform_id
                WHERE j.fic_id = f.fic_id
                ORDER BY v.freeform
            ) AS freeform

        FROM unnest(%s::bigint[]) AS f(fic_id)
        """,
        (fic_ids,),
    )

    rows = cur.fetchall()

    metadata_by_id = {
        row[0]: {
            "warning": row[1],
            "category": row[2],
            "fandom": row[3],
            "relationship": row[4],
            "character": row[5],
            "freeform": row[6],
        }
        for row in rows
    }

    for fic in fics:
        metadata = metadata_by_id.get(fic["fic_id"])

        if metadata:
            fic.update(metadata)

    return fics