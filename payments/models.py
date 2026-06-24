import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class Provider(models.TextChoices):
        PAYME = "payme", "Payme"
        STRIPE = "stripe", "Stripe"

    ext_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    # card number is hashed for lookup; raw number is never stored
    card_number_hash = models.CharField(max_length=64, db_index=True)
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    currency = models.CharField(max_length=3)  # UZS | USD
    provider = models.CharField(max_length=10, choices=Provider.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    provider_transaction_id = models.CharField(max_length=200, blank=True)
    provider_response = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    refund_id = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.ext_id} | {self.provider} | {self.status} | {self.amount} {self.currency}"
