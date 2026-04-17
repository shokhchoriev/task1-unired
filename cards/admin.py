from django.contrib import admin
from django import forms
from django.shortcuts import render, redirect
from django.urls import path
from .models import Card
from .services import import_cards_from_excel


class ExcelImportForm(forms.Form):
    file = forms.FileField()


class CardAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_card_number',
        'expire',
        'formatted_phone',
        'status',
        'balance'
    )

    def formatted_card_number(self, obj):
        return obj.formatted_card_number()

    def formatted_phone(self, obj):
        return obj.formatted_phone()
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-excel/', self.import_excel),
        ]
        return custom_urls + urls

    def import_excel(self, request):
        if request.method == "POST":
            form = ExcelImportForm(request.POST, request.FILES)
            if form.is_valid():
                success, errors = import_cards_from_excel(request.FILES["file"])

                self.message_user(
                    request,
                    f"{success} ta muvaffaqiyatli yuklandi, {len(errors)} ta xato"
                )

                request.session['errors'] = errors
                return redirect("..")
        else:
            form = ExcelImportForm()

        return render(request, "admin/import_excel.html", {"form": form})
    