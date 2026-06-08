from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "masked_secret")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("masked_secret",)
    exclude = ("secret",)

    @admin.display(description="Secret")
    def masked_secret(self, obj):
        if obj.secret:
            return f"{obj.secret[:6]}{'*' * (len(obj.secret) - 6)}"
        return "(not set)"
