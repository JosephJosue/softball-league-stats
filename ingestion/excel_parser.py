"""Excel / CSV reading.

Thin wrappers around pandas — they only extract a raw table. All mapping and
validation happens in ingestion.validation. Accept raw bytes so the caller
(Streamlit's UploadedFile) can be read multiple times without pointer issues.
"""

from __future__ import annotations

import io

import pandas as pd


def list_sheets(data: bytes) -> list[str]:
    """Sheet names in an .xlsx workbook."""
    return pd.ExcelFile(io.BytesIO(data), engine="openpyxl").sheet_names


def read_excel(data: bytes, sheet: str | int = 0) -> pd.DataFrame:
    """Read one sheet of an .xlsx workbook into a DataFrame (all cells as-is)."""
    return pd.read_excel(io.BytesIO(data), sheet_name=sheet, engine="openpyxl")


def read_csv(data: bytes) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    return pd.read_csv(io.BytesIO(data))
