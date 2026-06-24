from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from tgbot.helpers import get_user_cards
from tgbot.keyboards import main_menu


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Foydalanuvchi"
    await update.message.reply_text(
        f"👋 Salom, {name}!\n\n"
        "Bank botiga xush kelibsiz. Quyidagi buyruqlardan foydalaning:\n\n"
        "💳 /mycards — Kartalarim\n"
        "➕ /addcard — Yangi karta qo'shish\n"
        "🔗 /linkcard — Admin qo'shgan kartani ulash\n"
        "💸 /transfer — O'tkazma qilish\n"
        "📋 /history — O'tkazmalar tarixi\n"
        "🪪 /myid — Telegram ID ni ko'rish\n"
        "❌ /cancel — Amalni bekor qilish\n\n"
        "💎 <b>Tron (Nile testnet):</b>\n"
        "/tron_wallet — Hamyon yaratish / ko'rish\n"
        "/tron_balance — TRX balansi\n"
        "/tron_send — TRX yuborish\n"
        "/tron_history — Oxirgi 10 ta tranzaksiya",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🪪 <b>Sizning Telegram ma'lumotlaringiz:</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Ism: {user.first_name or '-'}\n"
        f"Username: @{user.username or '-'}\n\n"
        f"Admin panelda kartaning <b>tg_id</b> maydoniga "
        f"<code>{user.id}</code> qiymatini kiriting — "
        f"shunda karta botda ko'rinadi va OTP Telegramga keladi.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Amal bekor qilindi.", reply_markup=main_menu())
    return ConversationHandler.END


async def my_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    cards = await get_user_cards(tg_id)

    if not cards:
        await update.message.reply_text(
            "💳 Sizda hali karta yo'q.\n\n"
            "• /addcard — yangi karta qo'shish\n"
            "• /linkcard — admin qo'shgan kartani ulash\n"
            "• /myid — Telegram ID ni admin panelga qo'lda kiritish uchun",
            reply_markup=main_menu(),
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
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=main_menu())
