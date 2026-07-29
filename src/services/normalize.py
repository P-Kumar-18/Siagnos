import datetime
import decimal
import uuid
import numpy as np


def normalize_row(data):
    """
    Recursively converts a dict, list, or scalar containing
    non-JSON-serializable types into plain JSON-safe equivalents.
    Leaves every other type (int, float, str, bool, None) untouched.
    """
    if isinstance(data, dict):
        return {key: normalize_row(value) for key, value in data.items()}

    if isinstance(data, (list, tuple)):
        return [normalize_row(item) for item in data]

    if isinstance(data, (datetime.datetime, datetime.date)):
        return data.isoformat()

    if isinstance(data, decimal.Decimal):
        return float(data)

    if isinstance(data, uuid.UUID):
        return str(data)

    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data).decode("utf-8", errors="replace")

    if isinstance(data, np.generic):
        return data.item()

    return data