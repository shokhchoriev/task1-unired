import pandas as pd
from datetime import datetime
from django.core.exceptions import ValidationError
from .models import Card
from .utils import normalize_phone, normalize_card_number


def import_cards_from_excel(file):
    df = pd.read_excel(file)

    errors = []
    success = 0

    for index, row in df.iterrows():
        try:
            card_number = normalize_card_number(str(row.get('card_number')))
            phone = normalize_phone(str(row.get('phone')))
            expire_str = str(row.get('expire'))
            balance = float(row.get('balance', 0))

  
            expire_date = datetime.strptime(expire_str, "%m/%y").date()

            if not card_number:
                raise ValidationError("Card number bo‘sh")

            if balance < 0:
                raise ValidationError("Balance manfiy")

            Card.objects.update_or_create(
                card_number=card_number,
                defaults={
                    "phone": phone,
                    "expire_date": expire_date,
                    "balance": balance,
                    "status": "active"
                }
            )

            success += 1

        except Exception as e:
            errors.append(f"Row {index+1}: {str(e)}")

    return success, errors