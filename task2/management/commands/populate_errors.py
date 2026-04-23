from django.core.management.base import BaseCommand

from task2.models import Error


DEFAULT_ERRORS = [
    {
        "code": 32000,
        "en": "Internal server error",
        "ru": "Vnutrennyaya oshibka servera",
        "uz": "Ichki server xatosi",
    },
    {
        "code": 32701,
        "en": "Transfer with this ext_id already exists",
        "ru": "Perevod s takim ext_id uzhe sushchestvuet",
        "uz": "Bu ext_id bilan transfer allaqachon mavjud",
    },
    {
        "code": 32702,
        "en": "Insufficient balance",
        "ru": "Nedostatochno sredstv",
        "uz": "Balans yetarli emas",
    },
    {
        "code": 32703,
        "en": "Invalid currency",
        "ru": "Nekorrektnaya valyuta",
        "uz": "Noto'g'ri valyuta",
    },
    {
        "code": 32704,
        "en": "Object not found",
        "ru": "Ob'ekt ne nayden",
        "uz": "Obyekt topilmadi",
    },
    {
        "code": 32705,
        "en": "Invalid amount",
        "ru": "Nekorrektnaya summa",
        "uz": "Noto'g'ri summa",
    },
    {
        "code": 32708,
        "en": "Transfer is not in created state",
        "ru": "Perevod ne v sostoyanii created",
        "uz": "Transfer created holatida emas",
    },
    {
        "code": 32709,
        "en": "Invalid OTP",
        "ru": "Nevernyy OTP",
        "uz": "Noto'g'ri OTP",
    },
    {
        "code": 32710,
        "en": "Transfer cannot be cancelled",
        "ru": "Perevod nelzya otmenit",
        "uz": "Transferni bekor qilib bo'lmaydi",
    },
    {
        "code": 32711,
        "en": "OTP attempts exceeded",
        "ru": "Prevyshen limit popytok OTP",
        "uz": "OTP urinishlar limiti tugadi",
    },
]


class Command(BaseCommand):
    help = "Populate task2 Error table with default JSON-RPC business errors"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for item in DEFAULT_ERRORS:
            error_obj, created = Error.objects.get_or_create(
                code=item["code"],
                defaults={
                    "en": item["en"],
                    "ru": item["ru"],
                    "uz": item["uz"],
                },
            )

            if created:
                created_count += 1
                continue

            dirty_fields = []
            for field_name in ("en", "ru", "uz"):
                new_value = item[field_name]
                if getattr(error_obj, field_name) != new_value:
                    setattr(error_obj, field_name, new_value)
                    dirty_fields.append(field_name)

            if dirty_fields:
                error_obj.save(update_fields=dirty_fields)
                updated_count += 1
            else:
                unchanged_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "populate_errors done: "
                f"created={created_count}, updated={updated_count}, unchanged={unchanged_count}"
            )
        )
