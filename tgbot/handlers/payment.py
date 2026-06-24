from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from tgbot.helpers import (
    do_stripe_checkout,
    do_stripe_refund,
    get_payment_by_ext_id,
)
from tgbot.keyboards import cancel_keyboard, main_menu, payment_currency_keyboard
from tgbot.states import (
    PAY_AMOUNT,
    PAY_CURRENCY,
    PAY_REFUND_EXT_ID,
    PAY_STATUS_EXT_ID,
)

STATUS_EMOJIS = {"success": "✅", "failed": "❌", "pending": "⏳", "refunded": "🔄"}


# ─── /pay conversation ────────────────────────────────────────────────────────

async def pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "💳 <b>Stripe to'lov</b>\n\nTo'lov miqdorini kiriting:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return PAY_AMOUNT


async def pay_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _pay_cancel(update, context)

    text = update.message.text.strip().replace(",", ".")
    try:
        amount = Decimal(text)
        if amount < Decimal("1"):
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text("❌ Noto'g'ri miqdor. Kamida 1 bo'lishi kerak:")
        return PAY_AMOUNT

    context.user_data["pay_amount"] = str(amount)
    await update.message.reply_text(
        f"💰 Miqdor: <b>{amount}</b>\n\nValyutani tanlang:",
        parse_mode="HTML",
        reply_markup=payment_currency_keyboard(),
    )
    return PAY_CURRENCY


async def pay_currency_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    currency = query.data.replace("pay_currency_", "")
    tg_id = update.effective_user.id
    amount = context.user_data["pay_amount"]

    await query.edit_message_text(f"⏳ Checkout sessiyasi yaratilmoqda ({currency})...")

    checkout_url, payment = await do_stripe_checkout(amount, currency, tg_id)

    if not checkout_url:
        err_msg = payment.error_message or "Noma'lum xato"
        await query.message.reply_text(
            f"❌ <b>Xatolik:</b> {err_msg}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    else:
        await query.message.reply_text(
            f"💳 <b>Stripe to'lov</b>\n\n"
            f"💰 Miqdor: <b>{payment.amount} {payment.currency}</b>\n"
            f"🆔 ext_id: <code>{payment.ext_id}</code>\n\n"
            f"Quyidagi tugma orqali to'lovni amalga oshiring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Stripe orqali to'lash", url=checkout_url)
            ]]),
        )

    context.user_data.clear()
    return ConversationHandler.END


async def _pay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ To'lov bekor qilindi.", reply_markup=main_menu())
    return ConversationHandler.END


# ─── /payment_status conversation ────────────────────────────────────────────

async def payment_status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🔍 To'lov holatini tekshirish\n\next_id ni kiriting:",
        reply_markup=cancel_keyboard(),
    )
    return PAY_STATUS_EXT_ID


async def payment_status_ext_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        context.user_data.clear()
        await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_menu())
        return ConversationHandler.END

    ext_id = update.message.text.strip()
    payment = await get_payment_by_ext_id(ext_id)

    if payment is None:
        await update.message.reply_text(
            f"❌ <code>{ext_id}</code> bo'yicha to'lov topilmadi.",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    else:
        emoji = STATUS_EMOJIS.get(payment.status, "•")
        text = (
            f"{emoji} <b>To'lov holati</b>\n\n"
            f"Holat: <b>{payment.status}</b>\n"
            f"Miqdor: <b>{payment.amount} {payment.currency}</b>\n"
            f"Provaydar: {payment.provider}\n"
            f"ext_id: <code>{payment.ext_id}</code>"
        )
        if payment.error_message:
            text += f"\nXato: {payment.error_message}"
        if payment.refund_id:
            text += f"\nQaytarish IDsi: <code>{payment.refund_id}</code>"
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu())

    return ConversationHandler.END


# ─── /refund conversation ─────────────────────────────────────────────────────

async def refund_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🔄 <b>To'lovni qaytarish</b>\n\next_id ni kiriting:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return PAY_REFUND_EXT_ID


async def refund_ext_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        context.user_data.clear()
        await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_menu())
        return ConversationHandler.END

    ext_id = update.message.text.strip()
    await update.message.reply_text("⏳ Qaytarish amalga oshirilmoqda...")

    payment, error = await do_stripe_refund(ext_id)

    if error:
        await update.message.reply_text(
            f"❌ <b>Xatolik:</b> {error}",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            f"✅ <b>To'lov muvaffaqiyatli qaytarildi!</b>\n\n"
            f"Qaytarish IDsi: <code>{payment.refund_id}</code>\n"
            f"Miqdor: <b>{payment.amount} {payment.currency}</b>\n"
            f"ext_id: <code>{payment.ext_id}</code>",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END
