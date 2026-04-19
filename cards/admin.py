from django import forms
from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path, reverse

from .models import Card
from .services import import_cards_from_excel
from .utils import human_card, human_phone


class ExcelImportForm(forms.Form):
    file = forms.FileField()


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
        "phone",
        "balance",
    )

    search_fields = (
        "card_number",
        "phone",
    )

    @admin.display(description="Card Number")
    def readable_card_number(self, obj):
        return human_card(obj.card_number)

    @admin.display(description="Phone")
    def readable_phone(self, obj):
        return human_phone(obj.phone) if obj.phone else "-"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-excel/",
                self.admin_site.admin_view(self.import_excel),
                name="cards_card_import_excel",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_excel_url"] = reverse("admin:cards_card_import_excel")
        return super().changelist_view(request, extra_context=extra_context)

    def import_excel(self, request):
        if request.method == "POST":
            form = ExcelImportForm(request.POST, request.FILES)
            if form.is_valid():
                success, errors = import_cards_from_excel(request.FILES["file"])
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
        }
        return render(request, "admin/import_excel.html", context)
