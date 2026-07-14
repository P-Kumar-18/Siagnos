import os
import psycopg

from src.loader.config import VALUE_TABLE_MAPPING

from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

def fetch_lookup_maps(connection):
    lookup_maps = {}

    with connection.cursor() as cur:

        for key, (table_name, id_column, value_column) in VALUE_TABLE_MAPPING.items():

            cur.execute(
                f"""
                SELECT {id_column}, {value_column}
                FROM {table_name}
                """
            )

            rows = cur.fetchall()

            lookup_maps[key] = {
                value: id_
                for id_, value in rows
            }

    return lookup_maps