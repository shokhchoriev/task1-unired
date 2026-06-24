import re

from rest_framework import serializers

from .models import Payment


class PaymentRequestSerializer(serializers.Serializer):
    ext_id = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True, default=None)
    card_number = serializers.CharField(min_length=16, max_length=16)
    expire = serializers.CharField(max_length=7, help_text="MM/YY or MM/YYYY")
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=1)
    currency = serializers.ChoiceField(choices=["UZS", "USD"])
    provider = serializers.ChoiceField(choices=["payme", "stripe"])

    def validate_card_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Card number must contain only digits")
        return value

    def validate_expire(self, value):
        if not re.match(r"^\d{2}/(\d{2}|\d{4})$", value):
            raise serializers.ValidationError("Expiry must be MM/YY or MM/YYYY")
        return value


class PaymentResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "ext_id",
            "status",
            "provider",
            "provider_transaction_id",
            "amount",
            "currency",
            "error_message",
            "refund_id",
            "created_at",
        ]


class RefundRequestSerializer(serializers.Serializer):
    ext_id = serializers.CharField(max_length=100)
