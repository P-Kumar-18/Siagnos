from src.loader.config import TABLE_CONFIG, FIC_COLUMNS, VALUE_TABLE_MAPPING

import pandas as pd

def build_value_table(frame, column, value_column):
    # Flatten all values into a single list
    all_values = []

    for values in frame[column]:
        if values:
            all_values.extend(values)

    # Create unique sorted value table
    unique_values = sorted(set(all_values))

    value_table = pd.DataFrame(
            {value_column: sorted(set(all_values))}
        ).reset_index(drop=True)

    return value_table

def build_normalized_tables(df):
    df['fic_id'] = (
        df['url']
        .str.extract(r'/works/(\d+)')
        .astype('Int64')
    )

    duplicates_removed = (
        df['fic_id']
        .duplicated()
        .sum()
    )

    df = df.drop_duplicates(
        subset='fic_id',
        keep='first'
    ).reset_index(drop=True)

    df_core = df[FIC_COLUMNS].copy()

    df_core = df_core.rename(columns={
        'title': 'name'
    })

    value_tables = {}

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

    for key in lookup_maps:

        _, id_column, _ = VALUE_TABLE_MAPPING[key]

        rows = []

        for fic_id, values in df[['fic_id', key]].itertuples(index=False):

            if not values:
                continue

            for value in values:
                rows.append({
                    'fic_id': fic_id,
                    id_column: lookup_maps[key][value]
                })

        join_tables[key] = (
            pd.DataFrame(rows)
            .drop_duplicates()
            .sort_values(['fic_id', id_column])
            .reset_index(drop=True)
        )

    return join_tables