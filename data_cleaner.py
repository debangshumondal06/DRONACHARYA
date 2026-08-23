import csv
import math
from pathlib import Path


def to_number(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def analyze_csv(path, target_column=None):
    path = Path(path)

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            if not columns:
                raise ValueError("The CSV must contain a header row.")
            rows = [dict(row) for row in reader]
    except UnicodeDecodeError as error:
        raise ValueError("The CSV must be UTF-8 encoded.") from error
    except csv.Error as error:
        raise ValueError("The CSV could not be parsed.") from error

    if not rows:
        raise ValueError("The CSV must contain at least one data row.")

    numeric_columns = []
    numeric_counts = {}
    missing_cells = 0
    total_cells = len(rows) * len(columns)

    for column in columns:
        values = [to_number(row.get(column)) for row in rows]
        numeric_count = sum(value is not None for value in values)
        numeric_counts[column] = numeric_count
        missing_cells += sum(
            value is None or str(row.get(column, "")).strip() == ""
            for row, value in zip(rows, values)
        )
        if numeric_count >= max(3, math.ceil(len(rows) * 0.6)):
            numeric_columns.append(column)

    if target_column and target_column not in columns:
        raise ValueError(f'Target column "{target_column}" was not found in the CSV.')

    selected_target = target_column or (numeric_columns[-1] if numeric_columns else None)
    quality_score = round(
        max(0, 100 * (1 - missing_cells / max(total_cells, 1))),
        1,
    )

    return {
        "columns": columns,
        "row_count": len(rows),
        "numeric_columns": numeric_columns,
        "target_column": selected_target,
        "missing_cells": missing_cells,
        "quality_score": quality_score,
        "numeric_counts": numeric_counts,
        "rows": rows,
    }