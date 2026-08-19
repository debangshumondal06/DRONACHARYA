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
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def analyze_csv(file_path, requested_target=None):
    path = Path(file_path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            original_fields = reader.fieldnames or []
            rows = [dict(row) for row in reader]
    except UnicodeDecodeError as error:
        raise ValueError("The CSV must use UTF-8 text encoding.") from error
    except csv.Error as error:
        raise ValueError(f"Could not read the CSV file: {error}") from error

    columns = [name.strip() for name in original_fields if name and name.strip()]
    if not columns:
        raise ValueError("The CSV must contain a header row with column names.")
    if not rows:
        raise ValueError("The CSV does not contain any data rows.")

    cleaned_rows = [
        {column: (row.get(column, "") or "").strip() for column in columns}
        for row in rows
    ]

    missing_values = {
        column: sum(1 for row in cleaned_rows if row[column] == "")
        for column in columns
    }
    signatures = [tuple(row[column] for column in columns) for row in cleaned_rows]
    duplicate_count = len(signatures) - len(set(signatures))

    numeric_columns = []
    categorical_columns = []
    numeric_summary = {}
    for column in columns:
        values = [to_number(row[column]) for row in cleaned_rows]
        usable = [value for value in values if value is not None]
        if len(usable) >= max(3, math.ceil(len(cleaned_rows) * 0.5)):
            numeric_columns.append(column)
            numeric_summary[column] = {
                "count": len(usable),
                "minimum": round(min(usable), 3),
                "maximum": round(max(usable), 3),
                "average": round(sum(usable) / len(usable), 3),
            }
        else:
            categorical_columns.append(column)

    target_column = choose_target(columns, numeric_columns, requested_target)
    warnings = []
    for column, count in missing_values.items():
        if count:
            warnings.append(f"{column} has {count} missing value(s).")
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate row(s) were detected.")
    if not numeric_columns:
        warnings.append("No numeric column was found for the first prediction.")
    if len(cleaned_rows) < 10:
        warnings.append("The dataset has fewer than 10 rows; predictions may be unreliable.")

    total_cells = len(cleaned_rows) * len(columns)
    missing_cells = sum(missing_values.values())
    completeness = 1 - (missing_cells / total_cells if total_cells else 1)
    duplicate_factor = 1 - duplicate_count / len(cleaned_rows)
    size_factor = min(1, len(cleaned_rows) / 50)
    quality_score = round(max(0, min(100, (completeness * 0.6 + duplicate_factor * 0.2 + size_factor * 0.2) * 100)))

    return {
        "filename": path.name,
        "row_count": len(cleaned_rows),
        "column_count": len(columns),
        "columns": columns,
        "preview": cleaned_rows[:8],
        "missing_values": missing_values,
        "duplicate_count": duplicate_count,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "numeric_summary": numeric_summary,
        "target_column": target_column,
        "quality_score": quality_score,
        "warnings": warnings,
        "rows": cleaned_rows,
    }


def choose_target(columns, numeric_columns, requested_target):
    if requested_target:
        if requested_target not in columns:
            raise ValueError(f'The selected target column "{requested_target}" was not found.')
        if requested_target not in numeric_columns:
            raise ValueError("The selected target column must contain numeric values.")
        return requested_target

    preferred_words = ("yield", "production", "sales", "revenue", "output", "score", "amount", "risk")
    for column in numeric_columns:
        if any(word in column.lower() for word in preferred_words):
            return column
    return numeric_columns[-1] if numeric_columns else None
