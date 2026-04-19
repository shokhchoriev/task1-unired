from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .utils import human_card, human_phone


class Card(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("expired", "Expired"),
    ]

    card_number = models.CharField(max_length=16, unique=True, db_index=True)
    expire = models.CharField(max_length=7, help_text="Stored as YYYY-MM")
    phone = models.CharField(max_length=13, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("1200000000.00")),
        ],
    )

    class Meta:
        ordering = ["card_number"]

    def __str__(self):
        return self.formatted_card_number()

    def formatted_card_number(self):
        return human_card(self.card_number)

    def formatted_phone(self):
        if not self.phone:
            return "-"
        return human_phone(self.phone)
