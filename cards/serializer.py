from rest_framework import serializers
from .utils import format_expire
import re

from .models import Card
from .utils import (
    normalize_phone,
    format_card,
)
    
class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = "__all__"

    def validate_expire(self, value):
        if not re.match(r"^(0[1-9]|1[0-2])\/\d{2}$", value):
            raise serializers.ValidationError(
                "Expiry must be MM/YY format"
            )
        return value
    
    def validate_phone(self, value):
        return normalize_phone(value)

    def validate_card_number(self, value):
        return format_card(value)
    


def validate_expire(self, value):
    return format_expire(value)