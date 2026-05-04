import time
from decimal import Decimal

from asgiref.sync import sync_to_async


@sync_to_async
def get_user_cards(tg_id):
    from cards.models import Card
    return list(Card.objects.filter(tg_id=str(tg_id), status="active"))


@sync_to_async
def get_card_by_number(card_number):
    from cards.models import Card
    try:
        return Card.objects.get(card_number=card_number)
    except Card.DoesNotExist:
        return None


@sync_to_async
def create_card_db(tg_id, card_number, expire, phone, balance):
    from cards.models import Card
    try:
        card = Card.objects.create(
            tg_id=str(tg_id),
            card_number=card_number,
            expire=expire,
            phone=phone,
            status="active",
            balance=Decimal(str(balance)),
        )
        return card, None
    except Exception as exc:
        return None, str(exc)


@sync_to_async
def do_transfer_create(ext_id, sender_card_number, sender_card_expiry,
                       receiver_card_number, sending_amount, currency):
    from task2.views import transfer_create
    return transfer_create(
        ext_id=ext_id,
        sender_card_number=sender_card_number,
        sender_card_expiry=sender_card_expiry,
        receiver_card_number=receiver_card_number,
        sending_amount=sending_amount,
        currency=currency,
    )


@sync_to_async
def do_transfer_confirm(ext_id, otp):
    from task2.views import transfer_confirm
    return transfer_confirm(ext_id=ext_id, otp=otp)


@sync_to_async
def do_transfer_cancel(ext_id):
    from task2.views import transfer_cancel
    return transfer_cancel(ext_id=ext_id)


@sync_to_async
def get_user_history(tg_id, limit=10):
    from cards.models import Card
    from task2.models import Transfer
    from django.db.models import Q

    card_numbers = list(
        Card.objects.filter(tg_id=str(tg_id)).values_list("card_number", flat=True)
    )
    if not card_numbers:
        return []
    return list(
        Transfer.objects.filter(
            Q(sender_card_number__in=card_numbers) |
            Q(receiver_card_number__in=card_numbers)
        ).order_by("-created_at")[:limit]
    )


@sync_to_async
def link_card_to_tg(tg_id, card_number, expire_raw):
    from cards.models import Card
    from cards.utils import format_expire
    try:
        normalized = format_expire(expire_raw)
    except Exception:
        return None, "Muddat noto'g'ri formatda. MM/YY shaklida kiriting."

    try:
        card = Card.objects.get(card_number=card_number, expire=normalized)
    except Card.DoesNotExist:
        return None, "Karta topilmadi. Raqam yoki muddat noto'g'ri."

    card.tg_id = str(tg_id)
    card.save(update_fields=["tg_id"])
    return card, None


def make_ext_id(tg_id):
    return f"tg-{tg_id}-{int(time.time())}"
