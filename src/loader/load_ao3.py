from src.loader.cleaner import clean_dataframe
from src.loader.normalizer import build_normalized_tables, build_join_tables
from src.loader.validator import validate
from src.loader.database import get_connection, fetch_lookup_maps
from src.loader.inserter import insert_fics, insert_value_tables,insert_join_tables
from src.loader.config import LIST_COLUMNS

import pandas as pd


def load_ao3(csv_path: str):
    df_raw = pd.read_csv(csv_path)
    print(f"Loaded {len(df_raw)} rows from {csv_path}")

    # Cleaning
    df = clean_dataframe(df_raw)
    print(f"Cleaned dataframe, resulting in {len(df)} rows")

    # Normalize core + lookup values
    df, df_core, value_tables, duplicates_removed = (
        build_normalized_tables(df)
    )
    print(f"Normalized dataframe, resulting in {len(df_core)} unique fics (removed {duplicates_removed} duplicates)")

    connection = get_connection()
    print("Connected to the database")

    try:
        # Insert core fics
        insert_fics(connection, df_core)
        print(f"Inserted {len(df_core)} fics into the database")

        # Insert lookup values
        insert_value_tables(connection, value_tables)
        print(f"Inserted {len(value_tables)} value tables into the database")

        # Fetch DB-generated IDs
        lookup_maps = fetch_lookup_maps(connection)
        print(f"Fetched lookup maps for {len(lookup_maps)} value tables from the database")

        # Build join tables using real IDs
        join_tables = build_join_tables(
            df,
            lookup_maps
        )
        print(f"Built {len(join_tables)} join tables for the fics")

        # Validate everything
        validate(
            df,
            df_core,
            value_tables,
            join_tables,
            LIST_COLUMNS
        )
        print("Validation passed for all tables")

        # Insert joins
        insert_join_tables(
            connection,
            join_tables
        )
        print(f"Inserted {len(join_tables)} join tables into the database")

        connection.commit()
        print("All changes committed to the database")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
        print("Database connection closed")


if __name__ == "__main__":
    load_ao3("data/ao3_data.csv")