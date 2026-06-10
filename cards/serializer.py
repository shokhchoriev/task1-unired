import re

from rest_framework import serializers

from .models import Card
from .utils import format_card, format_expire, normalize_phone


class CardSerializer(serializers.ModelSerializer):
    card_number = serializers.CharField(max_length=16)

    class Meta:
        model = Card
        fields = ["id", "tg_id", "card_number", "expire", "phone", "status", "balance"]

    def validate_expire(self, value):
        if not re.match(r"^(0[1-9]|1[0-2])\/\d{2}$", value):
            raise serializers.ValidationError("Expiry must be MM/YY format")
        return value

    def validate_phone(self, value):
        return normalize_phone(value)

    def validate_card_number(self, value):
        return format_card(value)

    def create(self, validated_data):
        card_number = validated_data.pop("card_number")
        card = Card(**validated_data)
        card.card_number = card_number
        card.save()
        return card

    def update(self, instance, validated_data):
        card_number = validated_data.pop("card_number", None)
        if card_number is not None:
            instance.card_number = card_number
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance