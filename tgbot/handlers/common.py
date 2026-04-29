from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from tgbot.helpers import get_user_cards
from tgbot.keyboards import main_menu, sender_card_keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Foydalanuvchi"
    await update.message.reply_text(
        f"👋 Salom, {name}!\n\n"
        "Bank botiga xush kelibsiz. Quyidagi buyruqlardan foydalaning:\n\n"
        "💳 /mycards — Kartalarim\n"
        "➕ /addcard — Karta qo'shish\n"
        "💸 /transfer — O'tkazma qilish\n"
        "📋 /history — O'tkazmalar tarixi\n"
        "❌ /cancel — Amalni bekor qilish",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Amal bekor qilindi.", reply_markup=main_menu())
    return ConversationHandler.END


async def my_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    cards = await get_user_cards(tg_id)

    if not cards:
        await update.message.reply_text(
            "💳 Sizda hali karta yo'q.\n/addcard buyrug'i orqali karta qo'shing."
        )
        return

    lines = ["💳 <b>Sizning kartalaringiz:</b>\n"]
    for i, card in enumerate(cards, 1):
        lines.append(
            f"{i}. <code>{card.card_number[:4]} **** **** {card.card_number[-4:]}</code>\n"
            f"   Muddat: {card.expire}\n"
            f"   Balans: <b>{card.balance:,.2f} UZS</b>\n"
            f"   Status: {'✅ Faol' if card.status == 'active' else '❌ Nofaol'}\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
