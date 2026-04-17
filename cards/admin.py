from django.contrib import admin



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
    