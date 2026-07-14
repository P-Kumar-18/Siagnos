from src.loader.config import VALUE_TABLE_MAPPING, JOIN_TABLE_MAPPING

import pandas as pd

def sql_safe(value):
    return None if pd.isna(value) else value

def insert_fics(connection, df_core):
    query = """
    INSERT INTO fics (
        fic_id,
        url,
        name,
        author,
        summary,
        hits,
        bookmarks,
        kudos,
        current_chapters,
        total_chapters,
        words,
        last_date,
        status,
        language,
        rating
    )
    VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s
    )
    ON CONFLICT (fic_id)
    DO UPDATE SET
        name = COALESCE(EXCLUDED.name, fics.name),
        author = COALESCE(EXCLUDED.author, fics.author),
        summary = COALESCE(EXCLUDED.summary, fics.summary),
        hits = COALESCE(EXCLUDED.hits, fics.hits),
        bookmarks = COALESCE(EXCLUDED.bookmarks, fics.bookmarks),
        kudos = COALESCE(EXCLUDED.kudos, fics.kudos),
        current_chapters = COALESCE(EXCLUDED.current_chapters, fics.current_chapters),
        total_chapters = COALESCE(EXCLUDED.total_chapters, fics.total_chapters),
        words = COALESCE(EXCLUDED.words, fics.words),
        last_date = COALESCE(EXCLUDED.last_date, fics.last_date),
        status = COALESCE(EXCLUDED.status, fics.status),
        language = COALESCE(EXCLUDED.language, fics.language),
        rating = COALESCE(EXCLUDED.rating, fics.rating)
    """

    with connection.cursor() as cur:
        for row in df_core.itertuples(index=False):
            cur.execute(
                query,
                tuple(
                    sql_safe(value)
                    for value in (
                        row.fic_id,
                        row.url,
                        row.name,
                        row.author,
                        row.summary,
                        row.hits,
                        row.bookmarks,
                        row.kudos,
                        row.current_chapters,
                        row.total_chapters,
                        row.words,
                        row.last_date,
                        row.status,
                        row.language,
                        row.rating,
                    )
                )
            )


def insert_value_tables(connection, value_tables):

    with connection.cursor() as cur:

        for key, df in value_tables.items():

            table_name, _, value_column = VALUE_TABLE_MAPPING[key]

            query = f"""
            INSERT INTO {table_name} ({value_column})
            VALUES (%s)
            ON CONFLICT ({value_column})
            DO NOTHING
            """

            for value in df[value_column]:
                cur.execute(
                    query,
                    (value,)
                )


def insert_join_tables(connection, join_tables):

    with connection.cursor() as cur:

        for key, df in join_tables.items():

            table_name = JOIN_TABLE_MAPPING[key]

            _, id_column, _ = VALUE_TABLE_MAPPING[key]

            query = f"""
            INSERT INTO {table_name} (
                fic_id,
                {id_column}
            )
            VALUES (%s, %s)
            ON CONFLICT (fic_id, {id_column})
            DO NOTHING
            """

            for row in df.itertuples(index=False):
                cur.execute(
                    query,
                    (
                        row.fic_id,
                        getattr(row, id_column)
                    )
                )