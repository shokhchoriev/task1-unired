from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("💳 Kartalarim"), KeyboardButton("➕ Karta qo'shish")],
            [KeyboardButton("💸 O'tkazma"), KeyboardButton("📋 Tarix")],
        ],
        resize_keyboard=True,
    )


def sender_card_keyboard(cards):
    buttons = [
        [InlineKeyboardButton(
            f"💳 ...{c.card_number[-4:]}  |  {c.balance:,.0f} UZS",
            callback_data=f"sender_{c.card_number}",
        )]
        for c in cards
    ]
    return InlineKeyboardMarkup(buttons)


def history_card_keyboard(cards):
    buttons = [
        [InlineKeyboardButton(
            f"💳 ...{c.card_number[-4:]}",
            callback_data=f"hist_{c.card_number}",
        )]
        for c in cards
    ]
    return InlineKeyboardMarkup(buttons)


def currency_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 RUB (643)", callback_data="currency_643"),
            InlineKeyboardButton("🇺🇸 USD (840)", callback_data="currency_840"),
        ]
    ])


def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor qilish")]], resize_keyboard=True)
