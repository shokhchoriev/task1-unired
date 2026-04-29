from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from cards.utils import format_expire
from tgbot.helpers import create_card_db
from tgbot.keyboards import cancel_keyboard, main_menu
from tgbot.states import CARD_BALANCE, CARD_EXPIRY, CARD_NUMBER, CARD_PHONE


async def add_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "➕ <b>Yangi karta qo'shish</b>\n\n"
        "Karta raqamini kiriting (16 ta raqam):\n\n"
        "/cancel — bekor qilish",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return CARD_NUMBER


async def card_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _cancel(update, context)

    number = update.message.text.strip().replace(" ", "")
    if not number.isdigit() or len(number) != 16:
        await update.message.reply_text("❌ Noto'g'ri format. 16 ta raqam kiriting:")
        return CARD_NUMBER

    context.user_data["card_number"] = number
    await update.message.reply_text("📅 Kartaning amal qilish muddatini kiriting (MM/YY):")
    return CARD_EXPIRY


async def card_expiry_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _cancel(update, context)

    expiry_text = update.message.text.strip()
    try:
        normalized = format_expire(expiry_text)
    except Exception:
        await update.message.reply_text(
            "❌ Noto'g'ri format. MM/YY shaklida kiriting (masalan: 12/26):"
        )
        return CARD_EXPIRY

    context.user_data["expire"] = normalized
    await update.message.reply_text("📱 Telefon raqamingizni kiriting (+998XXXXXXXXX):")
    return CARD_PHONE


async def card_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _cancel(update, context)

    phone = update.message.text.strip()
    if not (phone.startswith("+") and phone[1:].isdigit() and len(phone) >= 10):
        await update.message.reply_text(
            "❌ Noto'g'ri format. +998XXXXXXXXX shaklida kiriting:"
        )
        return CARD_PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text(
        "💰 Boshlang'ich balansni kiriting (UZS, masalan: 100000):\n"
        "(0 kiritish ham mumkin)"
    )
    return CARD_BALANCE


async def card_balance_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await _cancel(update, context)

    text = update.message.text.strip().replace(",", "").replace(" ", "")
    try:
        balance = float(text)
        if balance < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri miqdor. Raqam kiriting:")
        return CARD_BALANCE

    tg_id = update.effective_user.id
    data = context.user_data

    card, error = await create_card_db(
        tg_id=tg_id,
        card_number=data["card_number"],
        expire=data["expire"],
        phone=data["phone"],
        balance=balance,
    )

    if error:
        msg = "❌ Bu karta yoki telefon allaqachon ro'yxatdan o'tgan." \
            if "UNIQUE" in error.upper() else f"❌ Xatolik: {error}"
        await update.message.reply_text(msg, reply_markup=main_menu())
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ <b>Karta muvaffaqiyatli qo'shildi!</b>\n\n"
        f"💳 Raqam: <code>{card.card_number[:4]} **** **** {card.card_number[-4:]}</code>\n"
        f"📅 Muddat: {card.expire}\n"
        f"💰 Balans: {card.balance:,.2f} UZS",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Amal bekor qilindi.", reply_markup=main_menu())
    return ConversationHandler.END
