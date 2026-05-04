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


# ─── CBU exchange rates ───────────────────────────────────────────────────────

_FALLBACK_RATES = {
    643: Decimal("140"),    # RUB
    840: Decimal("12500"),  # USD
}

_rate_cache: dict[int, Decimal] = {}
_cache_expires_at: float = 0.0
_CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
_CACHE_TTL = 3600  # seconds


def _fetch_cbu_rates() -> dict[int, Decimal]:
    """Fetch today's rates from cbu.uz; returns {numeric_code: uzs_per_unit}."""
    try:
        resp = httpx.get(_CBU_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rates: dict[int, Decimal] = {}
        for item in data:
            try:
                code = int(item["Code"])
                rate = Decimal(str(item["Rate"]))
                nominal = Decimal(str(item.get("Nominal", "1") or "1"))
                rates[code] = (rate / nominal).quantize(Decimal("0.0001"))
            except Exception:
                continue
        logger.info("[CBU] fetched %d exchange rates", len(rates))
        return rates
    except Exception:
        logger.warning("[CBU] failed to fetch rates, using fallback", exc_info=True)
        return {}


def _get_rate(currency: int) -> Decimal:
    """Return UZS-per-unit rate for the given ISO numeric currency code."""
    import time

    global _rate_cache, _cache_expires_at

    if time.time() > _cache_expires_at:
        fresh = _fetch_cbu_rates()
        if fresh:
            _rate_cache = fresh
            _cache_expires_at = time.time() + _CACHE_TTL

    if currency in _rate_cache:
        return _rate_cache[currency]

    if currency in _FALLBACK_RATES:
        logger.warning("[CBU] rate not found for %s, using fallback", currency)
        return _FALLBACK_RATES[currency]

    raise ValueError(f"Currency {currency} not allowed")


def calculate_exchange(amount: Decimal, currency: int) -> Decimal:
    """Return the UZS equivalent of `amount` units of `currency`."""
    if currency not in {643, 840}:
        raise ValueError("Currency not allowed")
    rate = _get_rate(currency)
    return (amount * rate).quantize(Decimal("0.01"))


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
