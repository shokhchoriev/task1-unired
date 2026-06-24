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
    link_card_expiry_received,
    link_card_number_received,
    link_card_start,
)
from tgbot.handlers.common import cancel_conv, help_cmd, my_cards, my_id, start
from tgbot.handlers.payment import (
    pay_amount_received,
    pay_currency_selected,
    pay_start,
    payment_status_ext_id_received,
    payment_status_start,
    refund_ext_id_received,
    refund_start,
)
from tgbot.handlers.tron import (
    tron_balance_cmd,
    tron_confirm,
    tron_history_cmd,
    tron_recv_addr,
    tron_send_amount,
    tron_send_start,
    tron_wallet_cmd,
    trx_buy_amount_received,
    trx_buy_start,
)
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
    LINK_CARD_EXPIRY,
    LINK_CARD_NUMBER,
    PAY_AMOUNT,
    PAY_CURRENCY,
    PAY_REFUND_EXT_ID,
    PAY_STATUS_EXT_ID,
    TRON_CONFIRM,
    TRON_RECV_ADDR,
    TRON_SEND_AMOUNT,
    TRF_AMOUNT,
    TRF_CURRENCY,
    TRF_OTP,
    TRF_RECEIVER,
    TRF_SELECT_SENDER,
    TRX_BUY_AMOUNT,
)

_CANCEL_FILTER = filters.Regex("^❌ Bekor qilish$")
_TEXT = filters.TEXT & ~filters.COMMAND


def run_bot() -> None:
    """Build and run the bot, blocking until stopped."""
    app = build_application()
    app.run_polling(drop_pending_updates=True, bootstrap_retries=-1)


def build_application() -> Application:
    token = settings.TELEGRAM_BOT_TOKEN

    add_card_conv = ConversationHandler(
        entry_points=[
            CommandHandler("addcard", add_card_start),
            MessageHandler(filters.Regex("^➕ Karta qo'shish$"), add_card_start),
        ],
        states={
            CARD_NUMBER:  [MessageHandler(_TEXT, card_number_received)],
            CARD_EXPIRY:  [MessageHandler(_TEXT, card_expiry_received)],
            CARD_PHONE:   [MessageHandler(_TEXT, card_phone_received)],
            CARD_BALANCE: [MessageHandler(_TEXT, card_balance_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    link_card_conv = ConversationHandler(
        entry_points=[
            CommandHandler("linkcard", link_card_start),
            MessageHandler(filters.Regex("^🔗 Karta ulash$"), link_card_start),
        ],
        states={
            LINK_CARD_NUMBER: [MessageHandler(_TEXT, link_card_number_received)],
            LINK_CARD_EXPIRY: [MessageHandler(_TEXT, link_card_expiry_received)],
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
            TRF_SELECT_SENDER: [CallbackQueryHandler(sender_selected, pattern=r"^sender_")],
            TRF_RECEIVER:      [MessageHandler(_TEXT, receiver_entered)],
            TRF_AMOUNT:        [MessageHandler(_TEXT, amount_entered)],
            TRF_CURRENCY:      [CallbackQueryHandler(currency_selected, pattern=r"^currency_")],
            TRF_OTP:           [MessageHandler(_TEXT, otp_entered)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    pay_conv = ConversationHandler(
        entry_points=[
            CommandHandler("pay", pay_start),
            MessageHandler(filters.Regex("^💳 Stripe to'lov$"), pay_start),
        ],
        states={
            PAY_AMOUNT:   [MessageHandler(_TEXT, pay_amount_received)],
            PAY_CURRENCY: [CallbackQueryHandler(pay_currency_selected, pattern=r"^pay_currency_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    payment_status_conv = ConversationHandler(
        entry_points=[CommandHandler("payment_status", payment_status_start)],
        states={
            PAY_STATUS_EXT_ID: [MessageHandler(_TEXT, payment_status_ext_id_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    refund_conv = ConversationHandler(
        entry_points=[CommandHandler("refund", refund_start)],
        states={
            PAY_REFUND_EXT_ID: [MessageHandler(_TEXT, refund_ext_id_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    tron_send_conv = ConversationHandler(
        entry_points=[
            CommandHandler("tron_send", tron_send_start),
            MessageHandler(filters.Regex("^🔄 Tron P2P$"), tron_send_start),
        ],
        states={
            TRON_RECV_ADDR:    [MessageHandler(_TEXT, tron_recv_addr)],
            TRON_SEND_AMOUNT:  [MessageHandler(_TEXT, tron_send_amount)],
            TRON_CONFIRM:      [MessageHandler(_TEXT, tron_confirm)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    trx_buy_conv = ConversationHandler(
        entry_points=[
            CommandHandler("trx_buy", trx_buy_start),
            MessageHandler(filters.Regex("^💎 TRX Sotib olish$"), trx_buy_start),
        ],
        states={
            TRX_BUY_AMOUNT: [MessageHandler(_TEXT, trx_buy_amount_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv),
            MessageHandler(_CANCEL_FILTER, cancel_conv),
        ],
    )

    app = Application.builder().token(token).build()

    # Simple commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(CommandHandler("mycards", my_cards))
    app.add_handler(CommandHandler("history", history))

    # Menu button shortcuts
    app.add_handler(MessageHandler(filters.Regex("^💳 Kartalarim$"), my_cards))
    app.add_handler(MessageHandler(filters.Regex("^📋 Tarix$"), history))
    app.add_handler(MessageHandler(filters.Regex("^🪪 Mening ID'm$"), my_id))
    app.add_handler(MessageHandler(filters.Regex("^💎 Tron Wallet$"), tron_wallet_cmd))

    # Tron commands
    app.add_handler(CommandHandler("tron_wallet", tron_wallet_cmd))
    app.add_handler(CommandHandler("tron_balance", tron_balance_cmd))
    app.add_handler(CommandHandler("tron_history", tron_history_cmd))

    # Conversations
    app.add_handler(add_card_conv)
    app.add_handler(link_card_conv)
    app.add_handler(transfer_conv)
    app.add_handler(pay_conv)
    app.add_handler(payment_status_conv)
    app.add_handler(refund_conv)
    app.add_handler(tron_send_conv)
    app.add_handler(trx_buy_conv)

    return app


if __name__ == "__main__":
    import django
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    run_bot()
