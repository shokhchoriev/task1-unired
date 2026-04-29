import django
from django.conf import settings
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from tgbot.handlers.card import (
    add_card_start,
    card_balance_received,
    card_expiry_received,
    card_number_received,
    card_phone_received,
)
from tgbot.handlers.common import cancel_conv, help_cmd, my_cards, start
from tgbot.handlers.transfer import (
    amount_entered,
    currency_selected,
    history,
    otp_entered,
    receiver_entered,
    sender_selected,
    transfer_start,
)
from tgbot.states import (
    CARD_BALANCE,
    CARD_EXPIRY,
    CARD_NUMBER,
    CARD_PHONE,
    TRF_AMOUNT,
    TRF_CURRENCY,
    TRF_OTP,
    TRF_RECEIVER,
    TRF_SELECT_SENDER,
)

_CANCEL_FILTER = filters.Regex("^❌ Bekor qilish$")


def build_application() -> Application:
    token = settings.TELEGRAM_BOT_TOKEN

    add_card_conv = ConversationHandler(
        entry_points=[
            CommandHandler("addcard", add_card_start),
            MessageHandler(filters.Regex("^➕ Karta qo'shish$"), add_card_start),
        ],
        states={
            CARD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, card_number_received)],
            CARD_EXPIRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, card_expiry_received)],
            CARD_PHONE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, card_phone_received)],
            CARD_BALANCE:[MessageHandler(filters.TEXT & ~filters.COMMAND, card_balance_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    transfer_conv = ConversationHandler(
        entry_points=[
            CommandHandler("transfer", transfer_start),
            MessageHandler(filters.Regex("^💸 O'tkazma$"), transfer_start),
        ],
        states={
            TRF_SELECT_SENDER: [
                CallbackQueryHandler(sender_selected, pattern=r"^sender_"),
            ],
            TRF_RECEIVER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receiver_entered),
            ],
            TRF_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered),
            ],
            TRF_CURRENCY: [
                CallbackQueryHandler(currency_selected, pattern=r"^currency_"),
            ],
            TRF_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, otp_entered),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mycards", my_cards))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(MessageHandler(filters.Regex("^💳 Kartalarim$"), my_cards))
    app.add_handler(MessageHandler(filters.Regex("^📋 Tarix$"), history))

    app.add_handler(add_card_conv)
    app.add_handler(transfer_conv)

    return app
