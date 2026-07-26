from src.loader import clean_dataframe, build_normalized_tables, build_join_tables, validate, filter_valid_rows, get_connection, fetch_lookup_maps, insert_fics, insert_value_tables, insert_join_tables, LIST_COLUMNS

import pandas as pd
from pathlib import Path


def load_csv(csv_path: str):
    # Reads raw data directly from a specified CSV location
    return pd.read_csv(csv_path)


def load_df(df: pd.DataFrame):
    # Returns an in-memory DataFrame as-is
    return df


def load_ao3(csv_path: str | None = None, df: pd.DataFrame | None = None) -> None:
    # Handle incoming arguments to safely assign the raw dataframe source
    if df is not None:
        df_raw = load_df(df)
    elif csv_path is not None:
        df_raw = load_csv(csv_path)
    else:
        raise ValueError("Either csv_path or df must be provided")

    print(f"Loaded {len(df_raw)} rows from {csv_path}")

    # --- Cleaning ---
    df = clean_dataframe(df_raw)
    print(f"Cleaned dataframe, resulting in {len(df)} rows")

    # --- Validation ---
    valid_rows, invalid_rows = filter_valid_rows(df, LIST_COLUMNS)
    df = pd.DataFrame(valid_rows)

    print(f"Validation complete: {len(valid_rows)} valid rows, {len(invalid_rows)} invalid rows")

    # Export malformed rows if any exist
    if invalid_rows:
        invalid_df = pd.DataFrame(invalid_rows)
        _path = Path(__file__).parent.parent.parent / "data" / "invalid" / "invalid_rows.csv"

        invalid_df.to_csv(_path, index=False)
        print(f"Saved invalid rows to {_path}")

    # --- Normalization ---
    # Split core data and mapped metadata attributes safely
    df, df_core, value_tables, duplicates_removed = build_normalized_tables(df)
    print(f"Normalized dataframe, resulting in {len(df_core)} unique fics (removed {duplicates_removed} duplicates)")

    # --- Database Transaction ---
    connection = get_connection()
    print("Connected to the database")

    try:
        # Insert work records
        insert_fics(connection, df_core)
        print(f"Inserted {len(df_core)} fics into the database")

        # Insert secondary attributes
        insert_value_tables(connection, value_tables)
        print(f"Inserted {len(value_tables)} value tables into the database")

        # Fetch IDs mapped during insertion
        lookup_maps = fetch_lookup_maps(connection)
        print(f"Fetched lookup maps for {len(lookup_maps)} value tables from the database")

        # Build many-to-many join references using retrieved database IDs
        join_tables = build_join_tables(df, lookup_maps)
        print(f"Built {len(join_tables)} join tables for the fics")

        # Verify integrity of generated schemas
        validate(df, df_core, value_tables, join_tables, LIST_COLUMNS)
        print("Validation passed for all tables")

        # Insert junction table references
        insert_join_tables(connection, join_tables)
        print(f"Inserted {len(join_tables)} join tables into the database")

        # Commit operations together safely
        connection.commit()
        print("All changes committed to the database")

    except Exception:
        connection.rollback()
        raise Exception("An error occurred during the database operations. All changes have been rolled back.")

    finally:
        connection.close()
        print("Database connection closed")


if __name__ == "__main__":
    _path = Path(__file__).parent.parent.parent / "data" / "raw" / "ao3_data.csv"
    load_ao3(_path)