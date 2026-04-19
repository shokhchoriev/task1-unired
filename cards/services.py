from pathlib import Path

from django.core.exceptions import ValidationError

from .models import Card
from .utils import (
    format_card,
    format_expire,
    format_phone,
    format_status,
    parse_balance,
)

REQUIRED_COLUMNS = {"card_number", "expire", "phone", "status", "balance"}


def _read_table(uploaded_file):
    try:
        import pandas as pd
    except ImportError as exc:
        raise ValidationError("pandas is required for import. Install it first.") from exc

    filename = getattr(uploaded_file, "name", "").lower()
    suffix = Path(filename).suffix

    if suffix == ".csv":
        return pd.read_csv(uploaded_file, dtype=str)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file, dtype=str)
    raise ValidationError("Only .xlsx, .xls, or .csv files are supported")


def import_cards_from_excel(uploaded_file):
    errors = []
    success = 0

    try:
        df = _read_table(uploaded_file)
    except Exception as exc:
        return 0, [f"File error: {exc}"]

    df.columns = [str(col).strip().lower() for col in df.columns]
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        missing_cols = ", ".join(sorted(missing))
        return 0, [f"Missing required columns: {missing_cols}"]

    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        try:
            card_number = format_card(row.get("card_number"))
            phone = format_phone(row.get("phone"))
            expire = format_expire(row.get("expire"))
            status = format_status(row.get("status"))
            balance = parse_balance(row.get("balance"))

            Card.objects.update_or_create(
                card_number=card_number,
                defaults={
                    "expire": expire,
                    "phone": phone,
                    "status": status,
                    "balance": balance,
                },
            )
            success += 1
        except Exception as exc:
            errors.append(f"Row {row_number}: {exc}")

    return success, errors
