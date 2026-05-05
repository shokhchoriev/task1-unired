import logging

import httpx
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def _send_telegram_report(message: str) -> bool:
    """Send a message to the configured report chat via Telegram Bot API."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_REPORT_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("[REPORT] TELEGRAM_BOT_TOKEN or TELEGRAM_REPORT_CHAT_ID not set")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        ok = resp.status_code == 200 and resp.json().get("ok")
        if ok:
            logger.info("[REPORT] Telegram message sent to chat_id=%s", chat_id)
        else:
            logger.warning("[REPORT] Telegram API error: %s", resp.text)
        return ok
    except Exception:
        logger.exception("[REPORT] Failed to send Telegram message")
        return False


def _build_stats_message(title: str) -> str:
    from cards.models import Card
    from task2.models import Transfer

    card_count = Card.objects.count()
    transfer_count = Transfer.objects.count()
    confirmed = Transfer.objects.filter(state=Transfer.State.CONFIRMED).count()
    cancelled = Transfer.objects.filter(state=Transfer.State.CANCELLED).count()
    created = Transfer.objects.filter(state=Transfer.State.CREATED).count()

    return (
        f"<b>{title}</b>\n\n"
        f"💳 Jami kartalar: <b>{card_count}</b>\n"
        f"🔄 Jami o'tkazmalar: <b>{transfer_count}</b>\n"
        f"  ✅ Tasdiqlangan: <b>{confirmed}</b>\n"
        f"  ❌ Bekor qilingan: <b>{cancelled}</b>\n"
        f"  ⏳ Kutilmoqda: <b>{created}</b>"
    )


@shared_task(name="task2.tasks.send_hourly_report")
def send_hourly_report():
    """Har soatda Telegram ga statistika yuboradi."""
    message = _build_stats_message("📊 Soatlik hisobot")
    _send_telegram_report(message)


@shared_task(name="task2.tasks.send_daily_report")
def send_daily_report():
    """Har kuni Telegram ga statistika yuboradi."""
    message = _build_stats_message("📈 Kunlik hisobot")
    _send_telegram_report(message)
