from django.contrib import admin
from django.utils.html import format_html

from .models import Error, Transfer


def _mask_card_number(card_number):
    if not card_number:
        return "-"
    digits = str(card_number).replace(" ", "")
    if len(digits) < 8:
        return digits
    return f"{digits[:4]} **** **** {digits[-4:]}"


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    save_on_top = True

    list_display = (
        "ext_id",
        "state_badge",
        "currency_label",
        "sending_amount",
        "receiving_amount",
        "sender_card_masked",
        "receiver_card_masked",
        "try_count",
        "created_at",
    )
    list_filter = (
        "state",
        "currency",
        "created_at",
        "confirmed_at",
        "cancelled_at",
    )
    search_fields = (
        "ext_id",
        "sender_card_number",
        "receiver_card_number",
        "sender_phone",
        "receiver_phone",
    )
    readonly_fields = (
        "created_at",
        "confirmed_at",
        "cancelled_at",
        "updated_at",
    )
    fieldsets = (
        ("Transfer", {"fields": ("ext_id", "state", "currency", "try_count")}),
        (
            "Card Details",
            {"fields": ("sender_card_number", "sender_card_expiry", "receiver_card_number")},
        ),
        ("Amounts", {"fields": ("sending_amount", "receiving_amount")}),
        ("Contact & OTP", {"fields": ("sender_phone", "receiver_phone", "otp")}),
        (
            "Timeline",
            {"fields": ("created_at", "confirmed_at", "cancelled_at", "updated_at")},
        ),
    )

    @admin.display(description="State", ordering="state")
    def state_badge(self, obj):
        colors = {
            Transfer.State.CREATED: "#f59e0b",
            Transfer.State.CONFIRMED: "#16a34a",
            Transfer.State.CANCELLED: "#dc2626",
        }
        color = colors.get(obj.state, "#6b7280")
        return format_html(
            '<span style="padding:2px 8px;border-radius:999px;color:white;background:{};">{}</span>',
            color,
            obj.get_state_display(),
        )

    @admin.display(description="Currency", ordering="currency")
    def currency_label(self, obj):
        mapping = {643: "RUB", 840: "USD"}
        return mapping.get(obj.currency, str(obj.currency))

    @admin.display(description="Sender Card", ordering="sender_card_number")
    def sender_card_masked(self, obj):
        return _mask_card_number(obj.sender_card_number)

    @admin.display(description="Receiver Card", ordering="receiver_card_number")
    def receiver_card_masked(self, obj):
        return _mask_card_number(obj.receiver_card_number)


@admin.register(Error)
class ErrorAdmin(admin.ModelAdmin):
    ordering = ("code",)
    list_display = ("code", "en", "ru", "uz")
    list_editable = ("en", "ru", "uz")
    search_fields = ("code", "en", "ru", "uz")
