from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from tgbot.helpers import (
    do_transfer_cancel,
    do_transfer_confirm,
    do_transfer_create,
    get_card_by_number,
    get_user_cards,
    get_user_history,
    make_ext_id,
)
from tgbot.keyboards import cancel_keyboard, currency_keyboard, main_menu, sender_card_keyboard
from tgbot.states import TRF_AMOUNT, TRF_CURRENCY, TRF_OTP, TRF_RECEIVER, TRF_SELECT_SENDER


# ─── Transfer: create flow ────────────────────────────────────────────────────

async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    tg_id = update.effective_user.id
    cards = await get_user_cards(tg_id)

    if not cards:
        await update.message.reply_text(
            "💳 Sizda faol karta yo'q.\n/addcard buyrug'i orqali karta qo'shing."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "💸 <b>O'tkazma qilish</b>\n\nQaysi kartadan pul yubormoqchisiz?",
        parse_mode="HTML",
        reply_markup=sender_card_keyboard(cards),
    )
    return TRF_SELECT_SENDER


async def sender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    card_number = query.data.replace("sender_", "")
    card = await get_card_by_number(card_number)
    if card is None:
        await query.edit_message_text("❌ Karta topilmadi. Qaytadan urinib ko'ring.")
        return ConversationHandler.END

    context.user_data["sender_card_number"] = card_number
    context.user_data["sender_card_expiry"] = card.expire

    await query.edit_message_text(
        f"✅ Tanlandi: <code>{card.card_number[:4]} **** **** {card.card_number[-4:]}</code>\n"
        f"💰 Balans: {card.balance:,.2f} UZS\n\n"
        f"Qabul qiluvchi karta raqamini kiriting (16 ta raqam):",
        parse_mode="HTML",
    )
    return TRF_RECEIVER


async def receiver_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _cancel(update, context)

    number = update.message.text.strip().replace(" ", "")
    if not number.isdigit() or len(number) != 16:
        await update.message.reply_text("❌ Noto'g'ri format. 16 ta raqam kiriting:")
        return TRF_RECEIVER

    receiver = await get_card_by_number(number)
    if receiver is None:
        await update.message.reply_text(
            "❌ Bu karta raqami topilmadi. Qaytadan kiriting:"
        )
        return TRF_RECEIVER

    context.user_data["receiver_card_number"] = number
    await update.message.reply_text(
        f"✅ Qabul qiluvchi: <code>{number[:4]} **** **** {number[-4:]}</code>\n\n"
        f"O'tkazma miqdorini kiriting:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TRF_AMOUNT


async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _cancel(update, context)

    text = update.message.text.strip().replace(",", "").replace(" ", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri miqdor. Musbat raqam kiriting:")
        return TRF_AMOUNT

    context.user_data["sending_amount"] = str(amount)
    await update.message.reply_text(
        f"💰 Miqdor: <b>{amount:,.2f}</b>\n\nValyutani tanlang:",
        parse_mode="HTML",
        reply_markup=currency_keyboard(),
    )
    return TRF_CURRENCY


async def currency_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    currency_code = int(query.data.replace("currency_", ""))
    currency_label = "RUB 🇷🇺" if currency_code == 643 else "USD 🇺🇸"
    context.user_data["currency"] = currency_code

    tg_id = update.effective_user.id
    ext_id = make_ext_id(tg_id)
    context.user_data["ext_id"] = ext_id

    await query.edit_message_text(
        f"⏳ O'tkazma yaratilmoqda...\n"
        f"Valyuta: {currency_label}"
    )

    result = await do_transfer_create(
        ext_id=ext_id,
        sender_card_number=context.user_data["sender_card_number"],
        sender_card_expiry=context.user_data["sender_card_expiry"],
        receiver_card_number=context.user_data["receiver_card_number"],
        sending_amount=context.user_data["sending_amount"],
        currency=currency_code,
    )

    if hasattr(result, "_error"):
        await query.edit_message_text(
            f"❌ Xatolik ({result._error.code}): {result._error.message}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        "✅ <b>O'tkazma yaratildi!</b>\n\n"
        "🔐 OTP kodi Telegramga yuborildi.\n"
        "Kodni quyida kiriting:",
        parse_mode="HTML",
    )
    return TRF_OTP


async def otp_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        ext_id = context.user_data.get("ext_id")
        if ext_id:
            await do_transfer_cancel(ext_id)
        return await _cancel(update, context)

    otp = update.message.text.strip()
    ext_id = context.user_data.get("ext_id")

    result = await do_transfer_confirm(ext_id=ext_id, otp=otp)

    if hasattr(result, "_error"):
        err = result._error
        if err.code == 32711:
            await update.message.reply_text(
                "❌ Urinishlar soni tugadi. O'tkazma bekor qilindi.",
                reply_markup=main_menu(),
            )
            context.user_data.clear()
            return ConversationHandler.END

        await update.message.reply_text(
            f"❌ {err.message}\nQaytadan kiriting:"
        )
        return TRF_OTP

    payload = result._value.result
    sender_num = context.user_data["sender_card_number"]
    receiver_num = context.user_data["receiver_card_number"]

    await update.message.reply_text(
        f"✅ <b>O'tkazma tasdiqlandi!</b>\n\n"
        f"💸 Miqdor: {context.user_data['sending_amount']}\n"
        f"💳 Yuboruvchi: <code>...{sender_num[-4:]}</code>\n"
        f"💳 Qabul qiluvchi: <code>...{receiver_num[-4:]}</code>\n"
        f"📌 Holat: {payload['state']}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ─── History ──────────────────────────────────────────────────────────────────

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    transfers = await get_user_history(tg_id)

    if not transfers:
        await update.message.reply_text(
            "📋 Hali o'tkazma yo'q.",
            reply_markup=main_menu(),
        )
        return

    STATE_EMOJI = {"created": "🕐", "confirmed": "✅", "cancelled": "❌"}
    lines = ["📋 <b>So'nggi 10 ta o'tkazma:</b>\n"]
    for t in transfers:
        emoji = STATE_EMOJI.get(t.state, "•")
        lines.append(
            f"{emoji} <code>{t.ext_id}</code>\n"
            f"   💸 {t.sending_amount} → {t.state}\n"
            f"   📅 {t.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ─── helpers ─────────────────────────────────────────────────────────────────

async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Amal bekor qilindi.", reply_markup=main_menu())
    return ConversationHandler.END
