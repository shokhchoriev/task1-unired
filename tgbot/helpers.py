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
    from config.security import _search_token
    try:
        return Card.objects.get(card_number_hash=_search_token(card_number))
    except Card.DoesNotExist:
        return None


@sync_to_async
def create_card_db(tg_id, card_number, expire, phone, balance):
    from cards.models import Card
    try:
        card = Card(
            tg_id=str(tg_id),
            expire=expire,
            phone=phone,
            status="active",
            balance=Decimal(str(balance)),
        )
        card.card_number = card_number
        card.save()
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

    card_numbers = [c.card_number for c in Card.objects.filter(tg_id=str(tg_id))]
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
        from config.security import _search_token
        card = Card.objects.get(card_number_hash=_search_token(card_number), expire=normalized)
    except Card.DoesNotExist:
        return None, "Karta topilmadi. Raqam yoki muddat noto'g'ri."

    card.tg_id = str(tg_id)
    card.save(update_fields=["tg_id"])
    return card, None


def make_ext_id(tg_id):
    return f"tg-{tg_id}-{int(time.time())}"


@sync_to_async
def get_payment_by_ext_id(ext_id: str):
    from payments.models import Payment
    try:
        return Payment.objects.get(ext_id=ext_id)
    except Payment.DoesNotExist:
        return None


@sync_to_async
def do_stripe_pay(card_number: str, expire: str, amount: str, currency: str, tg_id):
    from decimal import Decimal
    from payments.services import PaymentService
    service = PaymentService()
    ext_id = f"tg-stripe-{tg_id}-{int(time.time())}"
    return service.pay(
        card_number=card_number,
        expire=expire,
        amount=Decimal(amount),
        currency=currency,
        provider_name="stripe",
        ext_id=ext_id,
    )


@sync_to_async
def do_stripe_refund(ext_id: str):
    from payments.models import Payment
    from payments.services import PaymentService
    try:
        payment = Payment.objects.get(ext_id=ext_id, provider=Payment.Provider.STRIPE)
    except Payment.DoesNotExist:
        return None, "To'lov topilmadi"

    if payment.status == Payment.Status.REFUNDED:
        return payment, "To'lov allaqachon qaytarilgan"
    if payment.status != Payment.Status.SUCCESS:
        return None, f"Faqat muvaffaqiyatli to'lovni qaytarish mumkin (holat: {payment.status})"
    if not payment.provider_transaction_id:
        return None, "Stripe tranzaksiya IDsi yo'q"

    result = PaymentService().refund(payment)
    if result.success:
        payment.refresh_from_db()
        return payment, None
    return None, result.error or "Qaytarish amalga oshmadi"
