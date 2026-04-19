import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from cards.models import Card
from cards.utils import format_card, format_phone, human_card, human_phone


class Command(BaseCommand):
    help = "Export cards to CSV with optional filters"

    def add_arguments(self, parser):
        parser.add_argument("--status", choices=[choice[0] for choice in Card.STATUS_CHOICES])
        parser.add_argument("--card-number")
        parser.add_argument("--phone")
        parser.add_argument("--output", default="cards_export.csv")

    def handle(self, *args, **options):
        queryset = Card.objects.all()

        if options["status"]:
            queryset = queryset.filter(status=options["status"])

        if options["card_number"]:
            try:
                card_number = format_card(options["card_number"])
            except ValidationError as exc:
                raise CommandError(str(exc)) from exc
            queryset = queryset.filter(card_number=card_number)

        if options["phone"]:
            try:
                phone = format_phone(options["phone"])
            except ValidationError as exc:
                raise CommandError(str(exc)) from exc
            queryset = queryset.filter(phone=phone)

        output_file = options["output"]
        headers = ["card_number", "expire", "phone", "status", "balance"]

        with open(output_file, "w", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=headers)
            writer.writeheader()
            for card in queryset.iterator():
                writer.writerow(
                    {
                        "card_number": human_card(card.card_number),
                        "expire": card.expire,
                        "phone": human_phone(card.phone) if card.phone else "",
                        "status": card.status,
                        "balance": f"{card.balance:.2f}",
                    }
                )

        self.stdout.write(
            self.style.SUCCESS(f"{queryset.count()} ta karta '{output_file}' fayliga export qilindi.")
        )
