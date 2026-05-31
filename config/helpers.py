import re
import logging

class MaskingFormatter(logging.Formatter):
    def format(self, record):
        original_msg = super().format(record)
        return mask_sensitive_text(original_msg)

CARD_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d{6})\d{6}(\d{4})(?!\d)")
OTP_PATTERN = re.compile(r"(?i)(otp|otp_code|code|kod)(['\"\s:=]+)(\d{4,8})")
SENSITIVE_FIELD_NAMES = {
    "otp",
    "otp_code",
    "card_number",
    "sender_card_number",
    "receiver_card_number",
}


def mask_card_number(value):
    """Show only the first 6 and last 4 card digits in logs."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) < 10:
        return "***"
    return f"{digits[:6]}{'*' * (len(digits) - 10)}{digits[-4:]}"


def mask_otp(value):
    """Never write OTP values to logs."""
    if value is None:
        return None
    return "*****"


def mask_sensitive_text(text):
    """Mask card numbers and OTP-like fields inside free-form log text."""
    masked = CARD_NUMBER_PATTERN.sub(r"\1******\2", str(text))
    return OTP_PATTERN.sub(r"\1\2*****", masked)


def sanitize_for_log(value, key=None):
    """Recursively sanitize dictionaries/lists before passing them to loggers."""
    normalized_key = key.lower() if isinstance(key, str) else None

    if normalized_key in {"otp", "otp_code"}:
        return mask_otp(value)

    if normalized_key in SENSITIVE_FIELD_NAMES:
        return mask_card_number(value)

    if isinstance(value, dict):
        return {k: sanitize_for_log(v, k) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [sanitize_for_log(item) for item in value]

    if isinstance(value, str):
        return mask_sensitive_text(value)

    return value
