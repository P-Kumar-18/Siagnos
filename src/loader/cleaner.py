import ast
import re
import pandas as pd

from src.loader.config import (
    DEFAULT_ZERO_COLUMNS,
    INTEGER_COLUMNS,
    LIST_COLUMNS,
    TEXT_COLUMNS,
)


def clean_int(value):
    # Check if value is a missing representation in pandas
    if pd.isna(value):
        return pd.NA

    # Remove trailing/leading whitespaces and commas
    text = str(value).strip().replace(',', '')

    # Return missing value representation if the text is empty
    if text == '':
        return pd.NA

    return int(text)


def clean_status(value):
    # Check if value is a missing representation in pandas
    if pd.isna(value):
        return pd.NA

    # Clean and standardize casing of the string
    text = str(value).strip().lower()

    # Match and group completed statuses
    if text.startswith('completed'):
        return 'completed'

    # Match and group active ongoing statuses
    if text.startswith('updated'):
        return 'on_going'

    return text or pd.NA


def clean_date(value):
    # Check if value is a missing representation in pandas
    if pd.isna(value):
        return pd.NaT

    return pd.to_datetime(value, errors='coerce').date()


def clean_text(value):
    # Check if value is a missing representation in pandas
    if pd.isna(value):
        return pd.NA

    # Collapse sequential spaces into a single space
    text = re.sub(r'\s+', ' ', str(value)).strip()

    return text if text else pd.NA


def parse_list_literal(value):
    # Fast path if the input is already a valid list
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    # Return empty list if input is missing
    if pd.isna(value):
        return []

    # Handle string literal expressions of empty sets or nulls
    text = str(value).strip()

    if text in {'', '[]', 'nan', 'None'}:
        return []

    # Attempt to safely parse a list literal structure
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return [item.strip() for item in re.split(r'\s*,\s*', text) if item.strip()]

    # Strip items if parsing yields a valid list structure
    if isinstance(parsed, list):
        return [item.strip() for item in parsed if str(item).strip()]

    return [str(parsed).strip()] if str(parsed).strip() else []


def clean_dataframe(df_raw):
    # Make a copy to avoid mutating the original dataframe
    df = df_raw.copy()

    # Map text cleaning function across text columns
    for column in TEXT_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(clean_text)

    # Map integer cleaning function across numerical columns
    for column in INTEGER_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(clean_int)

    # Clean the status column if present
    if 'status' in df.columns:
        df['status'] = df['status'].map(clean_status)

    # Convert last date column to date objects if present
    if 'last_date' in df.columns:
        df['last_date'] = df['last_date'].map(clean_date)

    # Convert list string columns back to parsed arrays
    for column in LIST_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(parse_list_literal)

    # Ensure zero-default columns replace nulls and parse to safe nullable integers
    for column in DEFAULT_ZERO_COLUMNS:
        if column in df.columns:
            df[column] = df[column].fillna(0).astype('Int64')

    return df