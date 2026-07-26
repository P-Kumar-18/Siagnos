from src.loader import VALUE_TABLE_MAPPING

import os
import psycopg

from dotenv import load_dotenv

# Load environmental variables from .env file
load_dotenv()


def get_connection():
    # Attempt to retrieve database connection from a single unified URL
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return psycopg.connect(database_url)

    # Fall back to individual connection credentials if unified URL is not set
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )


def fetch_lookup_maps(connection):
    lookup_maps = {}

    with connection.cursor() as cur:
        # Retrieve IDs and matching values from configured static tables
        for key, (table_name, id_column, value_column) in VALUE_TABLE_MAPPING.items():
            cur.execute(
                f"""
                SELECT {id_column}, {value_column}
                FROM {table_name}
                """
            )

            rows = cur.fetchall()

            # Compact the mapping comprehension down to a single clean dictionary structure
            lookup_maps[key] = {value: id_ for id_, value in rows}

    return lookup_maps