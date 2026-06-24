import datetime
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from tgbot.helpers import (
    do_stripe_checkout_trx,
    do_tron_balance,
    do_tron_history,
    do_tron_send,
    get_or_create_tron_wallet,
    get_tron_wallet,
)
from tgbot.keyboards import cancel_keyboard, main_menu, tron_confirm_keyboard
from tgbot.states import TRON_CONFIRM, TRON_RECV_ADDR, TRON_SEND_AMOUNT, TRX_BUY_AMOUNT


# ─── /tron_wallet  (also "💎 Tron Wallet" button) ────────────────────────────

async def tron_wallet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    wallet, created = await get_or_create_tron_wallet(tg_id)

    if created:
        header = "💎 <b>Yangi Tron hamyoni yaratildi!</b>\n\n"
    else:
        header = "💎 <b>Sizning Tron hamyoningiz:</b>\n\n"

    balance = await do_tron_balance(wallet.address)

    await update.message.reply_text(
        f"{header}"
        f"📬 Manzil:\n<code>{wallet.address}</code>\n\n"
        f"💰 Balans: <b>{balance:.6f} TRX</b>\n\n"
        f"🌐 Nile testnet\n"
        f"💡 TRX olish uchun faucet: https://nileex.io/join/getJoinPage",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ─── /tron_balance ────────────────────────────────────────────────────────────

async def tron_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    wallet = await get_tron_wallet(tg_id)

    if wallet is None:
        await update.message.reply_text(
            "💎 Sizda hali Tron hamyoni yo'q.\n\n"
            "Yaratish uchun /tron_wallet yoki «💎 Tron Wallet» tugmasini bosing.",
            reply_markup=main_menu(),
        )
        return

    balance = await do_tron_balance(wallet.address)
    await update.message.reply_text(
        f"💰 <b>TRX balansi:</b> {balance:.6f} TRX\n"
        f"📬 <code>{wallet.address}</code>",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ─── /tron_send conversation ──────────────────────────────────────────────────

async def tron_send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    wallet = await get_tron_wallet(tg_id)

    if wallet is None:
        await update.message.reply_text(
            "💎 Avval hamyon yarating: /tron_wallet",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    balance = await do_tron_balance(wallet.address)
    context.user_data["tron_balance"] = balance
    context.user_data["tron_from_address"] = wallet.address

    await update.message.reply_text(
        f"💸 <b>TRX yuborish</b>\n\n"
        f"Joriy balans: <b>{balance:.6f} TRX</b>\n\n"
        f"Qabul qiluvchi Tron manzilini kiriting:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TRON_RECV_ADDR


async def tron_recv_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from tron.services import is_valid_address

    if update.message.text == "❌ Bekor qilish":
        return await _tron_cancel(update, context)

    addr = update.message.text.strip()
    if not is_valid_address(addr):
        await update.message.reply_text(
            "❌ Noto'g'ri Tron manzil. Manzil T harfi bilan boshlanib, 34 belgidan iborat bo'lishi kerak.\n\n"
            "Qayta kiriting:"
        )
        return TRON_RECV_ADDR

    context.user_data["tron_to_address"] = addr
    await update.message.reply_text(
        f"✅ Manzil: <code>{addr}</code>\n\n"
        f"Necha TRX yubormoqchisiz?",
        parse_mode="HTML",
    )
    return TRON_SEND_AMOUNT


async def tron_send_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _tron_cancel(update, context)

    text = update.message.text.strip().replace(",", ".")
    try:
        amount = Decimal(text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text("❌ Noto'g'ri miqdor. Musbat son kiriting:")
        return TRON_SEND_AMOUNT

    balance = context.user_data.get("tron_balance", Decimal("0"))
    if amount > balance:
        await update.message.reply_text(
            f"❌ Balans yetarli emas.\n"
            f"Mavjud: <b>{balance:.6f} TRX</b>, so'ralgan: <b>{amount} TRX</b>\n\n"
            f"Boshqa miqdor kiriting:",
            parse_mode="HTML",
        )
        return TRON_SEND_AMOUNT

    context.user_data["tron_amount"] = amount
    to_addr = context.user_data["tron_to_address"]

    await update.message.reply_text(
        f"📋 <b>Tasdiqlash</b>\n\n"
        f"📤 Yuboruvchi: <code>{context.user_data['tron_from_address']}</code>\n"
        f"📥 Qabul qiluvchi: <code>{to_addr}</code>\n"
        f"💰 Miqdor: <b>{amount} TRX</b>\n\n"
        f"Davom etasizmi?",
        parse_mode="HTML",
        reply_markup=tron_confirm_keyboard(),
    )
    return TRON_CONFIRM


async def tron_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "✅ Tasdiqlash":
        return await _tron_cancel(update, context)

    tg_id = update.effective_user.id
    to_address = context.user_data["tron_to_address"]
    amount = context.user_data["tron_amount"]

    await update.message.reply_text("⏳ Tranzaksiya yuborilmoqda...")

    txid, error = await do_tron_send(tg_id, to_address, amount)

    if error:
        await update.message.reply_text(
            f"❌ <b>Xatolik:</b> {error}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            f"✅ <b>TRX muvaffaqiyatli yuborildi!</b>\n\n"
            f"💰 Miqdor: <b>{amount} TRX</b>\n"
            f"📥 Qabul qiluvchi: <code>{to_address}</code>\n"
            f"🔗 TxID: <code>{txid}</code>\n\n"
            f"🌐 Nile explorer: https://nile.tronscan.org/#/transaction/{txid}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def _tron_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_menu())
    return ConversationHandler.END


# ─── TRX Sotib olish (Stripe → TRX) ─────────────────────────────────────────

async def trx_buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from django.conf import settings
    trx_price = getattr(settings, "TRX_PRICE_USD", "0.10")
    context.user_data.clear()
    await update.message.reply_text(
        f"💎 <b>TRX Sotib olish</b>\n\n"
        f"Narx: <b>1 TRX = ${trx_price} USD</b>\n\n"
        f"Necha TRX sotib olmoqchisiz?",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TRX_BUY_AMOUNT


async def trx_buy_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        context.user_data.clear()
        await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_menu())
        return ConversationHandler.END

    text = update.message.text.strip().replace(",", ".")
    try:
        trx_amount = Decimal(text)
        if trx_amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text("❌ Noto'g'ri miqdor. Musbat son kiriting:")
        return TRX_BUY_AMOUNT

    tg_id = update.effective_user.id

    wallet = await get_tron_wallet(tg_id)
    if wallet is None:
        await update.message.reply_text(
            "❌ Avval Tron hamyoni yarating:\n💎 Tron Wallet tugmasini bosing.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    await update.message.reply_text("⏳ Stripe Checkout yaratilmoqda...")

    checkout_url, payment, usd_amount = await do_stripe_checkout_trx(tg_id, trx_amount)

    if not checkout_url:
        err_msg = payment.error_message or "Noma'lum xato"
        await update.message.reply_text(
            f"❌ <b>Xatolik:</b> {err_msg}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            f"💎 <b>TRX Sotib olish</b>\n\n"
            f"Miqdor: <b>{trx_amount} TRX</b>\n"
            f"Narx: <b>${usd_amount} USD</b>\n"
            f"📬 Yetkazish manzili:\n<code>{wallet.address}</code>\n\n"
            f"To'lovdan so'ng TRX hamyoningizga avtomatik yuboriladi.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Stripe orqali to'lash", url=checkout_url)
            ]]),
        )

    context.user_data.clear()
    return ConversationHandler.END


# ─── /tron_history ────────────────────────────────────────────────────────────

async def tron_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    wallet = await get_tron_wallet(tg_id)

    if wallet is None:
        await update.message.reply_text(
            "💎 Sizda hali Tron hamyoni yo'q.\n\nYaratish uchun /tron_wallet",
            reply_markup=main_menu(),
        )
        return

    txs = await do_tron_history(wallet.address)

    if not txs:
        await update.message.reply_text(
            "📋 Tranzaksiyalar topilmadi.",
            reply_markup=main_menu(),
        )
        return

    lines = [f"📋 <b>So'nggi tranzaksiyalar ({wallet.address[:8]}...):</b>\n"]
    for i, tx in enumerate(txs, 1):
        ts = datetime.datetime.utcfromtimestamp(tx["timestamp_ms"] / 1000).strftime("%d.%m.%Y %H:%M")
        status_icon = "✅" if tx["status"] == "SUCCESS" else "❌"
        amount = tx["amount_trx"]

        if tx["type"] == "TransferContract":
            if tx["from_addr"] == wallet.address:
                direction = f"📤 -{amount} TRX → {tx['to_addr'][:8]}..."
            else:
                direction = f"📥 +{amount} TRX ← {tx['from_addr'][:8]}..."
        else:
            direction = f"📦 {tx['type']}"

        lines.append(
            f"{i}. {status_icon} {direction}\n"
            f"   🕐 {ts} | <code>{tx['txid'][:12]}...</code>"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
