import logging
import random
from decimal import Decimal

import httpx
from django.conf import settings

from .models import Transfer


logger = logging.getLogger(__name__)


class FakeNotificationService:
    """Sends OTP via real Telegram Bot API (falls back to log-only if token missing)."""

    def send_sms(self, phone, message):
        logger.info("[SMS] to=%s message=%s", phone, message)
        return {"channel": "sms", "to": phone, "sent": True}

    def send_telegram(self, tg_id, message):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not token or not str(tg_id).lstrip("-").isdigit():
            logger.info("[TELEGRAM_LOG] tg_id=%s message=%s", tg_id, message)
            return {"channel": "telegram", "to": tg_id, "sent": False}

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = httpx.post(
                url,
                json={"chat_id": int(tg_id), "text": message},
                timeout=5,
            )
            ok = resp.status_code == 200 and resp.json().get("ok")
            logger.info("[TELEGRAM] tg_id=%s sent=%s", tg_id, ok)
            return {"channel": "telegram", "to": tg_id, "sent": ok}
        except Exception:
            logger.warning("[TELEGRAM] send failed tg_id=%s", tg_id, exc_info=True)
            return {"channel": "telegram", "to": tg_id, "sent": False}

    def send_otp(self, phone, tg_id, otp):
        message = f"🔐 O'tkazma OTP kodi: {otp}\n\nUshbu kodni hech kimga bermang!"
        self.send_sms(phone=phone, message=message)
        self.send_telegram(tg_id=tg_id, message=message)
        return True


def generate_otp(length=6):
    return "".join([str(random.randint(0, 9)) for _ in range(length)])


def send_telegram_message(phone, message, chat_id=123456):
    logger.info("[FAKE_TELEGRAM_LEGACY] chat_id=%s phone=%s message=%s", chat_id, phone, message)
    return True


def validate_card(card_number):
    card_number = card_number.replace(" ", "")

    if not card_number.isdigit():
        return False

    total = 0
    reverse_digits = card_number[::-1]

    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0


def check_balance(card, amount):
    return card.balance >= amount


def calculate_exchange(amount, currency):
    rates = {
        643: Decimal("140"),  # RUB -> UZS
        840: Decimal("12500"),  # USD -> UZS
    }

    if currency not in rates:
        raise ValueError("Currency not allowed")

    return amount * rates[currency]


def get_transfer_by_ext_id(ext_id):
    try:
        return Transfer.objects.get(ext_id=ext_id)
    except Transfer.DoesNotExist:
        return None


def check_otp(transfer, otp):
    if transfer.try_count >= 3:
        raise Exception("Urinishlar soni tugagan")

    if transfer.otp != otp:
        transfer.try_count += 1
        transfer.save(update_fields=["try_count", "updated_at"])
        raise Exception(f"Noto‘g‘ri OTP, yana {3 - transfer.try_count} urinish qoldi")

    return True
