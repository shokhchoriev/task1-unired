from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from openpyxl import Workbook

from cards.models import Card
from cards.utils import format_card, format_phone, human_card, human_phone


class Command(BaseCommand):
    help = "Export cards to Excel (.xlsx) with optional filters"

    def add_arguments(self, parser):
        parser.add_argument("--status", choices=[choice[0] for choice in Card.STATUS_CHOICES])
        parser.add_argument("--card-number")
        parser.add_argument("--phone")
        parser.add_argument("--output", default="cards_export.xlsx")

    def handle(self, *args, **options):
        queryset = Card.objects.all()

        if options["status"]:
            queryset = queryset.filter(status=options["status"])

        if options["card_number"]:
            try:
                card_number = format_card(options["card_number"])
            except ValidationError as exc:
                raise CommandError(str(exc)) from exc
            from config.security import _search_token
            queryset = queryset.filter(card_number_hash=_search_token(card_number))

        if options["phone"]:
            try:
                phone = format_phone(options["phone"])
            except ValidationError as exc:
                raise CommandError(str(exc)) from exc
            queryset = queryset.filter(phone=phone)

        output_file = options["output"]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Cards"
        headers = ["card_number", "expire", "phone", "status", "balance"]
        sheet.append(headers)

        for card in queryset.iterator():
            sheet.append(
                [
                    human_card(card.card_number),
                    str(card.expire),
                    human_phone(card.phone) if card.phone else "",
                    card.status,
                    f"{card.balance:.2f}",
                ]
            )

        workbook.save(output_file)

        self.stdout.write(
            self.style.SUCCESS(f"{queryset.count()} ta karta '{output_file}' fayliga export qilindi.")
        )
