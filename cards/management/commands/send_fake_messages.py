from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from cards.models import Card
from cards.utils import card_mask, format_card, format_phone, prepare_message, send_message


class Command(BaseCommand):
    help = "Send fake Telegram messages to filtered cards"

    def add_arguments(self, parser):
        parser.add_argument("--status", choices=[choice[0] for choice in Card.STATUS_CHOICES])
        parser.add_argument("--card-number")
        parser.add_argument("--phone")
        parser.add_argument("--chat-id", type=int, default=12345)
        parser.add_argument("--lang", default="UZ")

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

        sent_count = 0
        for card in queryset.iterator():
            message = prepare_message(card.card_number, card.balance, lang=options["lang"])
            send_message(message, chat_id=options["chat_id"])
            self.stdout.write(f"[SENT] {card_mask(card.card_number)} | status={card.status}")
            sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"Jami {sent_count} ta fake xabar yuborildi."))
