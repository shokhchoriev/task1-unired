import logging

import httpx
from celery import shared_task
from django.conf import settings
from django.db.models import Sum, Count

logger = logging.getLogger(__name__)


def _send_telegram_report(message: str) -> bool:
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

    # ── Kartalar statistikasi ──────────────────────────────────────────────
    card_total   = Card.objects.count()
    card_active  = Card.objects.filter(status="active").count()
    card_inactive = Card.objects.filter(status="inactive").count()
    card_expired = Card.objects.filter(status="expired").count()
    total_balance = Card.objects.aggregate(s=Sum("balance"))["s"] or 0

    # ── O'tkazmalar statistikasi ───────────────────────────────────────────
    transfer_total     = Transfer.objects.count()
    confirmed_count    = Transfer.objects.filter(state=Transfer.State.CONFIRMED).count()
    cancelled_count    = Transfer.objects.filter(state=Transfer.State.CANCELLED).count()
    pending_count      = Transfer.objects.filter(state=Transfer.State.CREATED).count()

    confirmed_amount   = Transfer.objects.filter(
        state=Transfer.State.CONFIRMED
    ).aggregate(s=Sum("receiving_amount"))["s"] or 0

    pending_amount     = Transfer.objects.filter(
        state=Transfer.State.CREATED
    ).aggregate(s=Sum("sending_amount"))["s"] or 0

    return (
        f"<b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"💳 <b>KARTALAR</b>\n"
        f"  Jami: <b>{card_total}</b>\n"
        f"  ✅ Aktiv: <b>{card_active}</b>\n"
        f"  ⏸ Nofaol: <b>{card_inactive}</b>\n"
        f"  ❌ Muddati o'tgan: <b>{card_expired}</b>\n"
        f"  💰 Umumiy balans: <b>{total_balance:,.2f} UZS</b>\n\n"

        f"🔄 <b>O'TKAZMALAR</b>\n"
        f"  Jami: <b>{transfer_total}</b>\n"
        f"  ✅ Tasdiqlangan: <b>{confirmed_count}</b> "
        f"→ <b>{confirmed_amount:,.2f} UZS</b>\n"
        f"  ⏳ Kutilmoqda: <b>{pending_count}</b> "
        f"→ <b>{pending_amount:,.2f} UZS</b>\n"
        f"  ❌ Bekor qilingan: <b>{cancelled_count}</b>"
    )


@shared_task(name="task2.tasks.send_hourly_report")
def send_hourly_report():
    message = _build_stats_message("📊 Soatlik hisobot")
    _send_telegram_report(message)


@shared_task(name="task2.tasks.send_daily_report")
def send_daily_report():
    message = _build_stats_message("📈 Kunlik hisobot")
    _send_telegram_report(message)
