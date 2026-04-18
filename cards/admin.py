from django.contrib import admin
from .models import Card


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_card_number',
        'expire',
        'formatted_phone',
        'status',
        'balance'
    )

    list_filter = (
        'status',
        'expire',
        'balance',
    )

    search_fields = (
        'card_number',
        'phone',
    )

    def formatted_card_number(self, obj):
        return obj.formatted_card_number()

    def formatted_phone(self, obj):
        return obj.formatted_phone()