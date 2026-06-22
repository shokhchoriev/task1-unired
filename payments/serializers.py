import re

from rest_framework import serializers

from .models import Payment


class PaymentRequestSerializer(serializers.Serializer):
    card_number = serializers.CharField(min_length=16, max_length=16)
    expire = serializers.CharField(
        max_length=7,
        help_text="MM/YY yoki MM/YYYY formatda",
    )
    amount = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=1
    )
    currency = serializers.ChoiceField(choices=["UZS", "USD"])
    provider = serializers.ChoiceField(choices=["payme", "stripe"])

    def validate_card_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Karta raqami faqat raqamlardan iborat bo'lishi kerak")
        return value

    def validate_expire(self, value):
        # Accept MM/YY or MM/YYYY
        if not re.match(r"^\d{2}/(\d{2}|\d{4})$", value):
            raise serializers.ValidationError("Amal qilish muddati MM/YY yoki MM/YYYY formatida bo'lishi kerak")
        return value


class PaymentResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "status",
            "provider",
            "provider_transaction_id",
            "amount",
            "currency",
            "error_message",
            "created_at",
        ]
