from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html
from openpyxl import Workbook


from .models import Error, Transfer, Payment


def _mask_card_number(card_number):
    if not card_number:
        return "-"
    digits = str(card_number).replace(" ", "")
    if len(digits) < 8:
        return digits
    return f"{digits[:4]} **** **** {digits[-4:]}"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ext_id', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('ext_id', 'id')
    readonly_fields = ('id', 'created_at')


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    save_on_top = True
    actions = ["export_selected_transfers"]

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

    def export_selected_transfers(self, request, queryset):
        if not queryset.exists():
            self.message_user(request, "Hech qanday transfer tanlanmadi.", level=messages.WARNING)
            return

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=selected_transfers_export.xlsx"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Transfers"
        sheet.append([
            "ext_id",
            "state",
            "currency",
            "sending_amount",
            "receiving_amount",
            "sender_card_number",
            "receiver_card_number",
            "sender_phone",
            "receiver_phone",
            "try_count",
            "created_at",
        ])

        for transfer in queryset.order_by("-created_at"):
            sheet.append([
                transfer.ext_id,
                transfer.get_state_display(),
                transfer.currency,
                str(transfer.sending_amount),
                str(transfer.receiving_amount),
                transfer.sender_card_number,
                transfer.receiver_card_number,
                transfer.sender_phone,
                transfer.receiver_phone,
                transfer.try_count,
                transfer.created_at,
            ])

        workbook.save(response)
        return response

    export_selected_transfers.short_description = "Export selected transfers to Excel"


@admin.register(Error)
class ErrorAdmin(admin.ModelAdmin):
    ordering = ("code",)
    list_display = ("code", "en", "ru", "uz")
    list_editable = ("en", "ru", "uz")
    search_fields = ("code", "en", "ru", "uz")
