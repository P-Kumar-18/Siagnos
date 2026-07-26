from src.loader import TABLE_CONFIG, FIC_COLUMNS, VALUE_TABLE_MAPPING

import pandas as pd


def build_value_table(frame, column, value_column):
    # Flatten all tag lists from the specified column into a single collection
    all_values = []

    for values in frame[column]:
        if values:
            all_values.extend(values)

    # Dedup and sort values (retaining your original variables)
    unique_values = sorted(set(all_values))

    # Construct the unique sorted DataFrame representing the lookup table
    value_table = pd.DataFrame(
        {value_column: sorted(set(all_values))}
    ).reset_index(drop=True)

    return value_table


def build_normalized_tables(df):
    # Calculate the exact number of duplicates removed based on the primary key
    duplicates_removed = df['fic_id'].duplicated().sum()

    # Deduplicate the dataset based on fic_id
    df = df.drop_duplicates(
        subset='fic_id',
        keep='first'
    ).reset_index(drop=True)

    # Extract columns destined for the main fics table
    df_core = df[FIC_COLUMNS].copy()

    # Align naming conventions with the target database schema
    df_core = df_core.rename(columns={'title': 'name'})

    # Process and sanitize text summary fields to safeguard database insertion
    df_core["summary"] = df["summary"].fillna("").astype(str).tolist()

    value_tables = {}

    # Extract distinct lookup tables dynamically for warnings, fandoms, relationships, etc.
    for column, _, value_column in TABLE_CONFIG:
        if column in df.columns:
            value_tables[column] = build_value_table(
                df,
                column,
                value_column
            )
    
    return df, df_core, value_tables, duplicates_removed


def build_join_tables(df, lookup_maps):
    join_tables = {}

    # Build relational records linking works with generated metadata primary keys
    for key in lookup_maps:
        _, id_column, _ = VALUE_TABLE_MAPPING[key]

        rows = []

        # Iterate directly across the working dataset to match keys to database lookups
        for fic_id, values in df[['fic_id', key]].itertuples(index=False):
            if not values:
                continue

            for value in values:
                rows.append({
                    'fic_id': fic_id,
                    id_column: lookup_maps[key][value]
                })

        # Structure the finished list of mappings into a cleaned join dataset
        join_tables[key] = (
            pd.DataFrame(
                rows,
                columns=['fic_id', id_column]
            )
            .drop_duplicates()
            .sort_values(['fic_id', id_column])
            .reset_index(drop=True)
        )

    return join_tables