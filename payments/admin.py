from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "ext_id", "provider", "status", "amount", "currency", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("ext_id", "provider_transaction_id", "card_number_hash")
    readonly_fields = (
        "card_number_hash",
        "provider_response",
        "provider_transaction_id",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
