from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.db import connection
from openpyxl import Workbook

from .models import Card
from .services import import_cards_from_excel
from .utils import card_mask, human_phone


class ExcelImportForm(forms.Form):
    file = forms.FileField()


class PhoneUcellFilter(admin.SimpleListFilter):
    title = "Phone +99850"
    parameter_name = "phone_ucell"

    def lookups(self, request, model_admin):
        return (("yes", "+99850 (Ucell)"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(phone__startswith="+99850")
        return queryset


class BalanceGreaterThan1000Filter(admin.SimpleListFilter):
    title = "Balance > 1000"
    parameter_name = "balance_gt_1000"

    def lookups(self, request, model_admin):
        return (("yes", "1000 dan yuqori"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(balance__gt=1000)
        return queryset


class BalanceLessThan1000Filter(admin.SimpleListFilter):
    title = "Balance < 1000"
    parameter_name = "balance_lt_1000"

    def lookups(self, request, model_admin):
        return (("yes", "1000 dan past"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(balance__lt=1000)
        return queryset


class RichestCardsFilter(admin.SimpleListFilter):
    title = "Eng ko'p puli borlar"
    parameter_name = "richest_cards"

    def lookups(self, request, model_admin):
        return (("top5", "Top 5 balance"),)

    def queryset(self, request, queryset):
        if self.value() != "top5":
            return queryset
        top5_ids = list(
            Card.objects.order_by("-balance").values_list("pk", flat=True)[:5]
        )
        return queryset.filter(pk__in=top5_ids)


class TopTransactionsFilter(admin.SimpleListFilter):
    title = "Top operatsiyalar"
    parameter_name = "top_transactions"

    def lookups(self, request, model_admin):
        return (("top5", "Top 5 cards"),)

    def queryset(self, request, queryset):
        if self.value() != "top5":
            return queryset

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT card_number FROM (
                        SELECT sender_card_number AS card_number, COUNT(*) AS tx_count
                        FROM task2_transfer GROUP BY sender_card_number
                        UNION ALL
                        SELECT receiver_card_number AS card_number, COUNT(*) AS tx_count
                        FROM task2_transfer GROUP BY receiver_card_number
                    ) AS all_tx
                    GROUP BY card_number
                    ORDER BY SUM(tx_count) DESC
                    LIMIT 5
                """)
                plain_numbers = [row[0] for row in cursor.fetchall()]
            # Convert plain card numbers (from Transfer) to search hashes
            from config.security import _search_token
            hashes = [_search_token(cn) for cn in plain_numbers if cn]
            return queryset.filter(card_number_hash__in=hashes)
        except Exception:
            return queryset.none()


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    change_list_template = "admin/cards/card/change_list.html"
    list_display = (
        "readable_card_number",
        "expire",
        "readable_phone",
        "status",
        "balance",
    )

    list_filter = (
        "status",
        "expire",
        PhoneUcellFilter,
        BalanceGreaterThan1000Filter,
        BalanceLessThan1000Filter,
        RichestCardsFilter,
        TopTransactionsFilter,
    )

    actions = ["export_selected_cards"]

    # card_number_hash is the only searchable DB column; phone is still plain.
    search_fields = ("phone",)

    @admin.display(description="Card Number")
    def readable_card_number(self, obj):
        # Decrypt via property then apply ****1234 mask
        return card_mask(obj.card_number)

    @admin.display(description="Phone")
    def readable_phone(self, obj):
        if not obj.phone:
            return "-"
        try:
            return human_phone(obj.phone)
        except ValidationError:
            return obj.phone

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-excel/",
                self.admin_site.admin_view(self.import_excel),
                name="cards_card_import_excel",
            ),
            path(
                "export-xlsx/",
                self.admin_site.admin_view(self.export_xlsx),
                name="cards_card_export_xlsx",
            ),
        ]
        return custom_urls + urls

    def get_filtered_queryset(self, request):
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)

    def export_xlsx(self, request):
        queryset = self.get_filtered_queryset(request)
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=cards_export.xlsx"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Cards"
        sheet.append(["card_number", "expire", "phone", "status", "balance"])

        for card in queryset.order_by("card_number_hash"):
            sheet.append([
                card_mask(card.card_number),
                str(card.expire),
                card.phone or "",
                card.status,
                f"{card.balance:.2f}",
            ])

        workbook.save(response)
        return response

    def export_selected_cards(self, request, queryset):
        if not queryset.exists():
            queryset = self.get_filtered_queryset(request)

        if not queryset.exists():
            self.message_user(request, "Hech qanday karta tanlanmadi.", level=messages.WARNING)
            return

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = "attachment; filename=selected_cards_export.xlsx"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Selected Cards"
        sheet.append(["card_number", "expire", "phone", "status", "balance"])

        for card in queryset.order_by("card_number_hash"):
            sheet.append([
                card_mask(card.card_number),
                str(card.expire),
                card.phone or "",
                card.status,
                f"{card.balance:.2f}",
            ])

        workbook.save(response)
        return response

    export_selected_cards.short_description = "Export selected or filtered cards to Excel"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["current_query_string"] = request.GET.urlencode()

        try:
            from task2.models import Transfer
            from config.security import _search_token

            # 1. Duplicate cards (by hash — same hash means same card number)
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT card_number_hash FROM cards_card
                        GROUP BY card_number_hash HAVING COUNT(*) > 1
                    ) AS dups
                """)
                extra_context["duplicate_cards_count"] = cursor.fetchone()[0]

            # 2. Unique card numbers that appear in any Transfer row
            transfer_plain = set(
                Transfer.objects.values_list("sender_card_number", flat=True)
            ) | set(
                Transfer.objects.values_list("receiver_card_number", flat=True)
            )
            transfer_plain.discard(None)
            extra_context["unique_transfer_cards_count"] = len(transfer_plain)
            extra_context["unique_senders_count"] = extra_context["unique_transfer_cards_count"]

            # 3. Cards that never appear in any transfer
            if transfer_plain:
                transfer_hashes = {_search_token(cn) for cn in transfer_plain}
                extra_context["unused_cards_count"] = Card.objects.exclude(
                    card_number_hash__in=transfer_hashes
                ).count()
            else:
                extra_context["unused_cards_count"] = Card.objects.count()

            # 4. Unique sender phones
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(DISTINCT sender_phone) FROM task2_transfer"
                )
                extra_context["unique_sender_phones"] = cursor.fetchone()[0]

            # 5. Cards with balance > 1000
            extra_context["high_balance_count"] = Card.objects.filter(
                balance__gt=1000
            ).count()

        except Exception:
            pass

        extra_context["import_excel_url"] = reverse("admin:cards_card_import_excel")
        extra_context["export_csv_url"] = reverse("admin:cards_card_export_xlsx")
        extra_context["all_cards_url"] = reverse("admin:cards_card_changelist")

        return super().changelist_view(request, extra_context=extra_context)

    def get_import_filter(self, request):
        phone_ucell = request.GET.get("phone_ucell")
        balance_gt_1000 = request.GET.get("balance_gt_1000")
        balance_lt_1000 = request.GET.get("balance_lt_1000")
        balance_range = request.GET.get("balance_range")
        status_exact = request.GET.get("status__exact")
        expire_exact = request.GET.get("expire__exact")
        top_transactions = request.GET.get("top_transactions")
        richest_cards = request.GET.get("richest_cards")

        top5_card_numbers = None
        if top_transactions == "top5":
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT card_number FROM (
                            SELECT sender_card_number AS card_number, COUNT(*) AS tx_count
                            FROM task2_transfer GROUP BY sender_card_number
                            UNION ALL
                            SELECT receiver_card_number AS card_number, COUNT(*) AS tx_count
                            FROM task2_transfer GROUP BY receiver_card_number
                        ) AS all_tx
                        GROUP BY card_number
                        ORDER BY SUM(tx_count) DESC
                        LIMIT 5
                    """)
                    top5_card_numbers = [row[0] for row in cursor.fetchall()]
            except Exception:
                top5_card_numbers = []
        if richest_cards == "top5":
            try:
                # Decrypt via property to get plain numbers for row comparison
                top5_card_numbers = [
                    c.card_number for c in Card.objects.order_by("-balance")[:5]
                ]
            except Exception:
                top5_card_numbers = []

        def row_filter(row):
            if phone_ucell == "yes" and not str(row.get("phone", "")).startswith("+99850"):
                return False
            if balance_gt_1000 == "yes" and row.get("balance") is not None:
                if row["balance"] <= 1000:
                    return False
            if balance_lt_1000 == "yes" and row.get("balance") is not None:
                if row["balance"] >= 1000:
                    return False
            if balance_range == "gt_100" and row.get("balance") is not None:
                if row["balance"] <= 100:
                    return False
            if balance_range == "lt_100" and row.get("balance") is not None:
                if row["balance"] >= 100 or row["balance"] <= 0:
                    return False
            if balance_range == "zero" and row.get("balance") is not None:
                if row["balance"] != 0:
                    return False
            if status_exact and str(row.get("status", "")).lower() != str(status_exact).lower():
                return False
            if expire_exact and str(row.get("expire", "")) != str(expire_exact):
                return False
            if top5_card_numbers is not None:
                return row.get("card_number") in top5_card_numbers
            return True

        return row_filter

    def import_excel(self, request):
        if request.method == "POST":
            form = ExcelImportForm(request.POST, request.FILES)
            if form.is_valid():
                filter_func = self.get_import_filter(request)
                success, errors = import_cards_from_excel(
                    request.FILES["file"], row_filter=filter_func
                )
                self.message_user(
                    request,
                    f"{success} ta karta muvaffaqiyatli import qilindi.",
                    level=messages.SUCCESS,
                )

                if errors:
                    for error in errors[:20]:
                        self.message_user(request, error, level=messages.WARNING)
                    if len(errors) > 20:
                        self.message_user(
                            request,
                            f"Yana {len(errors) - 20} ta xato bor, faylni tekshiring.",
                            level=messages.WARNING,
                        )

                return redirect("..")
        else:
            form = ExcelImportForm()

        context = {
            "form": form,
            "opts": self.model._meta,
            "title": "Import cards from Excel/CSV",
            "current_query_string": request.GET.urlencode(),
        }
        return render(request, "admin/import_excel.html", context)
