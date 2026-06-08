import base64
import hashlib
import logging
import re
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ValidationError

LOGGER = logging.getLogger(__name__)

MAX_BALANCE = Decimal("1200000000.00")
ALLOWED_STATUSES = {"active", "inactive", "expired"}


def _is_empty(value):
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "(empty)"}


def format_card(raw_card):
    if _is_empty(raw_card):
        raise ValidationError("Card number is empty")

    digits = re.sub(r"\D", "", str(raw_card))
    if len(digits) != 16:
        raise ValidationError("Card number must contain exactly 16 digits")
    return digits


def human_card(card_number):
    digits = format_card(card_number)
    return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def card_mask(card_number):
    digits = format_card(card_number)
    return f"{digits[:4]}********{digits[-4:]}"


PHONE_REGEX = re.compile(r"^\+998\d{9}$")


def format_phone(raw_phone):
    if _is_empty(raw_phone):
        return None

    digits = re.sub(r"\D", "", str(raw_phone))
    if len(digits) == 7:

        digits = f"99899{digits}"
    elif len(digits) == 9:
        digits = f"998{digits}"
    elif len(digits) == 12 and digits.startswith("998"):
        pass
    else:
        raise ValidationError("Phone must be 9 digits or start with 998")

    normalized = f"+{digits}"
    if not PHONE_REGEX.match(normalized):
        raise ValidationError("Phone must match +998XXXXXXXXX format")
    return normalized


def human_phone(phone):
    try:
        normalized = format_phone(phone)
    except ValidationError:
        return str(phone).strip() if not _is_empty(phone) else "-"

    if not normalized:
        return "-"

    digits = normalized[1:]
    return f"+{digits[:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"


def phone_mask(phone):
    try:
        normalized = format_phone(phone)
    except ValidationError:
        return str(phone).strip() if not _is_empty(phone) else "-"

    if not normalized:
        return "-"

    digits = normalized[1:]
    return f"+{digits[:3]} {digits[3:5]} *** ** {digits[-2:]}"


def format_expire(raw_expire):
    if _is_empty(raw_expire):
        raise ValidationError("Expire value is empty")

    if hasattr(raw_expire, "year") and hasattr(raw_expire, "month"):
        year, month = raw_expire.year, raw_expire.month
        return f"{int(year):04d}-{int(month):02d}"

    text = str(raw_expire).strip()
    compact = text.replace(" ", "")

    patterns = [
        r"^(?P<year>\d{4})[-/.](?P<month>\d{1,2})$",
        r"^(?P<month>\d{1,2})[-/.](?P<year2>\d{2})$",
        r"^(?P<month>\d{1,2})[-/.](?P<year>\d{4})$",
        r"^(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.]\d{1,2}$",
        r"^(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.]\d{1,2}\s+\d{1,2}:\d{2}:\d{2}$",
    ]

    for pattern in patterns:
        match = re.match(pattern, compact)
        if not match:
            continue

        month = int(match.group("month"))
        if match.groupdict().get("year2"):
            year = 2000 + int(match.group("year2"))
        else:
            year = int(match.group("year"))

        if not 1 <= month <= 12:
            break
        return f"{year:04d}-{month:02d}"

    raise ValidationError(f"Unsupported expire format: {raw_expire}")


def format_status(raw_status):
    if _is_empty(raw_status):
        raise ValidationError("Status is empty")

    status = str(raw_status).strip().lower()
    if status not in ALLOWED_STATUSES:
        raise ValidationError(f"Invalid status: {raw_status}")
    return status


def parse_balance(raw_balance):
    if _is_empty(raw_balance):
        raise ValidationError("Balance is empty")

    if isinstance(raw_balance, Decimal):
        amount = raw_balance
    elif isinstance(raw_balance, (int, float)):
        amount = Decimal(str(raw_balance))
    else:
        cleaned = str(raw_balance).strip().replace(" ", "").replace(",", "")
        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValidationError(f"Invalid balance: {raw_balance}") from exc

    if amount < Decimal("0") or amount > MAX_BALANCE:
        raise ValidationError("Balance must be between 0 and 1.2 billion UZS")

    return amount.quantize(Decimal("0.01"))


def prepare_message(card_number, balance, lang="UZ"):
    amount = parse_balance(balance)
    formatted_card = human_card(card_number)
    if str(lang).upper() == "UZ":
        return (
            f"Sizning kartangiz {formatted_card} aktiv va foydalanishga "
            f"{amount:,.2f} UZS mavjud!"
        )
    return (
        f"Your card {formatted_card} is active and you have "
        f"{amount:,.2f} UZS available!"
    )


def send_message(message, chat_id=12345):
    LOGGER.info("Fake Telegram send -> chat_id=%s | message=%s", chat_id, message)
    return True


def normalize_card_number(card_number):
    return format_card(card_number)


def normalize_phone(phone):
    return format_phone(phone)

import os


def get_env(key, default=None):
    return os.getenv(key, default)


def hash_request(*parts):
    """Build a stable SHA-256 hex digest from request-identifying parts.

    Used as a Redis cache key for rate limiting / deduplication, e.g.
    ``hash_request(ip, "transfer.confirm", ext_id)`` so that limiter counters
    are scoped per IP+method+ext_id rather than per raw request body.

    Args:
        *parts: Any number of values (IP, method name, ext_id, ...). ``None``
            values are skipped; everything else is stringified.

    Returns:
        str: 64-character lowercase hex SHA-256 digest.
    """
    raw = "|".join(str(part) for part in parts if part is not None)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _encryption_key():
    """Derive a 32-byte urlsafe-base64 Fernet key from ENCRYPTION_KEY/SECRET_KEY."""
    secret = get_env("ENCRYPTION_KEY") or get_env("SECRET_KEY") or "insecure-default-key"
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(value):
    """Encrypt a value into an opaque Fernet token (AES-128-CBC + HMAC-SHA256).

    The symmetric key is derived from the ``ENCRYPTION_KEY`` env var (falling
    back to ``SECRET_KEY``), so no extra key material needs to be generated.

    Args:
        value: Any value; coerced to ``str`` before encryption. ``None`` passes through.

    Returns:
        str | None: URL-safe base64 token, or ``None`` if ``value`` is ``None``.
    """
    if value is None:
        return None
    return Fernet(_encryption_key()).encrypt(str(value).encode("utf-8")).decode("utf-8")


def decrypt(token):
    """Decrypt a token produced by :func:`encrypt` back into its original string.

    Args:
        token: The Fernet token returned by :func:`encrypt`. ``None`` passes through.

    Returns:
        str | None: The original plaintext, or ``None`` if ``token`` is ``None``
        or the token is invalid/tampered with.
    """
    if token is None:
        return None
    try:
        return Fernet(_encryption_key()).decrypt(str(token).encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask_card(card):
    return card_mask(card)


def mask_otp(otp):
    return "*" * len(str(otp))