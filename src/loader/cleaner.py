from src.loader.config import INTEGER_COLUMNS, LIST_COLUMNS, TEXT_COLUMNS, DEFAULT_ZERO_COLUMNS

import pandas as pd
import re
import ast

def clean_int(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().replace(',', '')
    if text == '':
        return pd.NA
    return int(text)


def clean_status(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text.startswith('completed'):
        return 'completed'
    if text.startswith('updated'):
        return 'on_going'
    return text or pd.NA


def clean_date(value):
    if pd.isna(value):
        return pd.NaT
    return pd.to_datetime(value, errors='coerce').date()


def clean_text(value):
    if pd.isna(value):
        return pd.NA
    text = re.sub(r'\s+', ' ', str(value)).strip()
    return text if text else pd.NA


def parse_list_literal(value):
    if pd.isna(value):
        return []
    text = str(value).strip()
    if text in {'', '[]', 'nan', 'None'}:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return [item.strip() for item in re.split(r'\s*,\s*', text) if item.strip()]
    if isinstance(parsed, list):
        return [item.strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def clean_dataframe(df_raw):
    df = df_raw.copy()

    for column in TEXT_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(clean_text)

    for column in INTEGER_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(clean_int)

    if 'status' in df.columns:
        df['status'] = df['status'].map(clean_status)

    if 'last_date' in df.columns:
        df['last_date'] = df['last_date'].map(clean_date)

    for column in LIST_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(parse_list_literal)

    for column in DEFAULT_ZERO_COLUMNS:
        if column in df.columns:
            df[column] = df[column].fillna(0).astype('Int64')

    return df