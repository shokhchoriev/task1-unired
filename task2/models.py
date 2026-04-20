from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

class Transfer(models.Model):
    class State(models.TextChoices):
        CREATED = "created", "Created"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    ext_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True
    )

    sender_card_number = models.CharField(max_length=16, db_index=True)
    receiver_card_number = models.CharField(max_length=16)

    sender_card_expiry = models.CharField(max_length=5)  

    sender_phone = models.CharField(max_length=20, null=True, blank=True)
    receiver_phone = models.CharField(max_length=20, null=True, blank=True)

    sending_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    receiving_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    currency = models.IntegerField()  

    state = models.CharField(
        max_length=10,
        choices=State.choices,
        default=State.CREATED
    )

    try_count = models.PositiveIntegerField(default=0)

    otp = models.CharField(max_length=6)

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ext_id} - {self.state}"
    

class Error(models.Model):
    code = models.IntegerField(unique=True)
    en = models.CharField(max_length=100)
    ru = models.CharField(max_length=100)
    uz = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code} - {self.en}"
    
    
