from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .utils import format_card, human_card, human_phone


class Card(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("expired", "Expired"),
    ]

    tg_id = models.CharField(max_length=20)
    # card_number is stored encrypted; card_number_hash is used for DB lookups.
    card_number_encrypted = models.TextField(blank=True, default="")
    card_number_hash = models.CharField(
        max_length=64, unique=True, db_index=True, blank=True, default=""
    )
    expire = models.CharField(max_length=7, help_text="Stored as YYYY-MM")
    phone = models.CharField(max_length=13, unique=True, db_index=True)
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
        ordering = ["card_number_hash"]

    # ── card_number property ──────────────────────────────────────────────────

    @property
    def card_number(self) -> str:
        """Return the decrypted 16-digit card number."""
        if not self.card_number_encrypted:
            return ""
        from config.security import decrypt_card
        return decrypt_card(self.card_number_encrypted)

    @card_number.setter
    def card_number(self, value: str) -> None:
        """Encrypt *value* and update the search hash atomically."""
        if not value:
            self.card_number_encrypted = ""
            self.card_number_hash = ""
            return
        from config.security import encrypt_card, _search_token
        plain = format_card(value)          # normalise to 16-digit string
        self.card_number_encrypted = encrypt_card(plain)
        self.card_number_hash = _search_token(plain)

    # ── helpers ───────────────────────────────────────────────────────────────

    def __str__(self):
        return self.formatted_card_number()

    def formatted_card_number(self):
        return human_card(self.card_number)

    def formatted_phone(self):
        if not self.phone:
            return "-"
        try:
            return human_phone(self.phone)
        except ValidationError:
            return self.phone or "-"
