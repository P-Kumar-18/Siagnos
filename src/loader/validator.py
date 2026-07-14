def validate(
    df,
    df_core,
    value_tables,
    join_tables,
    list_columns
):
    assert df_core['fic_id'].notna().all()
    assert df_core['fic_id'].is_unique
    assert df_core[['url', 'name', 'hits', 'bookmarks', 'kudos', 'current_chapters', 'words', 'language', 'rating']].notna().all().all()
    for column in list_columns:
        if column in df.columns:
            assert df[column].map(lambda value: isinstance(value, list)).all()
    for table in join_tables.values():
        assert table['fic_id'].isin(df_core['fic_id']).all()
    for table in join_tables.values():
        assert table.drop_duplicates().shape[0] == table.shape[0]
    for name, table in value_tables.items():
        assert table.drop_duplicates().shape[0] == table.shape[0]