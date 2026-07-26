class ValidationError(Exception):
    pass


def validate_row(row, list_columns):
    if row["fic_id"] is None:
        raise ValidationError("Missing fic_id")

    required_columns = ["url", "title", "hits", "bookmarks", "kudos", "current_chapters", "words", "language", "rating"]

    for column in required_columns:
        if row[column] is None:
            raise ValidationError(f"Missing required field: {column}")

    for column in list_columns:
        if column in row and not isinstance(row[column], list):
            raise ValidationError(f"{column} must be a list, got {type(row[column]).__name__}")


def filter_valid_rows(df, list_columns):
    valid_rows = []
    invalid_rows = []

    for index, row in df.iterrows():
        try:
            validate_row(row, list_columns)
            valid_rows.append(row.to_dict())
        except ValidationError as e:
            invalid_rows.append({"row_number": index, "fic_id": row.get("fic_id"), "error": str(e)})

    return valid_rows, invalid_rows


def validate(df, df_core, value_tables, join_tables, list_columns):
    assert df_core['fic_id'].notna().all()
    assert df_core['fic_id'].is_unique

    for table in join_tables.values():
        assert table['fic_id'].isin(df_core['fic_id']).all()

    for table in join_tables.values():
        assert table.drop_duplicates().shape[0] == table.shape[0]

    for _, table in value_tables.items():
        assert table.drop_duplicates().shape[0] == table.shape[0]