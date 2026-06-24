from django.contrib import admin

from .models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("tg_id", "address", "created_at")
    search_fields = ("tg_id", "address")
    readonly_fields = ("address", "encrypted_private_key", "created_at")
