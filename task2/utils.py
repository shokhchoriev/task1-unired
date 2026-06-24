import logging
import random
from decimal import Decimal
import time
import functools
import inspect

import httpx
from django.conf import settings

from decimal import Decimal, InvalidOperation
from config.helpers import mask_card_number, mask_sensitive_text, sanitize_for_log
from .models import Transfer




request_logger = logging.getLogger("task2.request")

def log_transfer_method(func):
    """Decorator that logs method name, payload, response, and elapsed time.

    Wraps any JSON-RPC handler decorated with ``@method``. On each call it
    records the function name, the full argument payload, the return value,
    execution time in seconds, and a SUCCESS/ERROR status to
    ``task2.request`` logger.

    Args:
        func (Callable): The RPC handler function to wrap.

    Returns:
        Callable: Wrapped function with identical signature.

    Example::

        @method(name="transfer.create")
        @log_transfer_method
        def transfer_create(ext_id, ...):
            ...
        # Logs: "Method: transfer_create | Status: SUCCESS | ... | Time: 0.0123s"
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            bound_args = inspect.signature(func).bind_partial(*args, **kwargs)
            request_payload = sanitize_for_log(bound_args.arguments)
        except Exception:
            request_payload = sanitize_for_log({"args": args, "kwargs": kwargs})
        
        try:
            response = func(*args, **kwargs)
            status = "SUCCESS"
        except Exception as e:
            response = {"error": mask_sensitive_text(str(e))}
            status = "ERROR"
            raise e
        finally:
            end_time = time.time()
            processing_time = end_time - start_time
            
            log_entry = (
                f"Method: {func.__name__} | Status: {status} | "
                f"Payload: {repr(request_payload)} | "
                f"Response: {repr(sanitize_for_log(response))} | "
                f"Time: {processing_time:.4f}s"
            )
            request_logger.info(log_entry)
            
        return response
    return wrapper

def _parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


logger = logging.getLogger(__name__)


class FakeNotificationService:
    """Sends OTP via real Telegram Bot API (falls back to log-only if token missing)."""

    def send_sms(self, phone, message):
        logger.info("[SMS] to=%s message=%s", phone, mask_sensitive_text(message))
        return {"channel": "sms", "to": phone, "sent": True}

    def send_telegram(self, tg_id, message):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not token or not str(tg_id).lstrip("-").isdigit():
            logger.info(
                "[TELEGRAM_LOG] tg_id=%s message=%s",
                tg_id,
                mask_sensitive_text(message),
            )
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
        """Send the OTP to the user via both SMS and Telegram simultaneously.

        Dispatches the OTP message through two channels: ``send_sms`` (always
        logs, simulates SMS) and ``send_telegram`` (real Telegram Bot API call
        when ``TELEGRAM_BOT_TOKEN`` is set, otherwise logs only).

        Args:
            phone (str): Sender's phone number in E.164 format (e.g. ``+998901234567``).
            tg_id (str | int): Sender's Telegram chat ID. Non-numeric values
                trigger log-only mode without an API call.
            otp (str): 6-digit one-time password to deliver.

        Returns:
            bool: Always ``True`` (delivery status is logged, not raised).

        Example::

            FakeNotificationService().send_otp(
                phone="+998901234567", tg_id="123456789", otp="******"
            )
        """
        message = f"🔐 O'tkazma OTP kodi: {otp}\n\nUshbu kodni hech kimga bermang!"
        self.send_sms(phone=phone, message=message)
        self.send_telegram(tg_id=tg_id, message=message)
        return True


def generate_otp(length=6):
    return "".join([str(random.randint(0, 9)) for _ in range(length)])


def send_telegram_message(phone, message, chat_id=123456):
    logger.info(
        "[FAKE_TELEGRAM_LEGACY] chat_id=%s phone=%s message=%s",
        chat_id,
        phone,
        mask_sensitive_text(message),
    )
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
    """Convert a foreign-currency amount to UZS using live CBU rates.

    Fetches today's rates from cbu.uz (cached in-process for 1 hour). Falls
    back to hardcoded rates (RUB=140, USD=12500) if the API is unreachable.

    Args:
        amount (Decimal): Positive amount in the source currency.
        currency (int): ISO 4217 numeric code — 643 (RUB) or 840 (USD).

    Returns:
        Decimal: Equivalent amount in UZS, rounded to 2 decimal places.

    Raises:
        ValueError: If ``currency`` is not in {643, 840}.

    Example::

        calculate_exchange(Decimal("100"), 840)
        # → Decimal("1250000.00")  (at rate 12500 UZS/USD)
    """
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
        raise Exception(f"Noto’g’ri OTP, yana {3 - transfer.try_count} urinish qoldi")

    return True


def send_payment_notification(tg_id, payment) -> bool:
    """Send a Stripe payment status update to a user’s Telegram chat."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token or not tg_id:
        logger.warning("[PAYMENT_NOTIFY] Missing token or tg_id=%s", tg_id)
        return False

    status_emojis = {"success": "✅", "failed": "❌", "pending": "⏳", "refunded": "🔄"}
    emoji = status_emojis.get(payment.status, "•")
    text = (
        f"{emoji} <b>To’lov holati</b>\n\n"
        f"Holat: <b>{payment.status.upper()}</b>\n"
        f"Miqdor: <b>{payment.amount} {payment.currency}</b>\n"
        f"ext_id: <code>{payment.ext_id}</code>"
    )
    if payment.error_message:
        text += f"\n❗ Xato: {payment.error_message}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": int(tg_id), "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        ok = resp.status_code == 200 and resp.json().get("ok")
        if not ok:
            logger.warning("[PAYMENT_NOTIFY] API error for tg_id=%s: %s", tg_id, resp.text[:200])
        return ok
    except Exception:
        logger.exception("[PAYMENT_NOTIFY] Failed for tg_id=%s", tg_id)
        return False
