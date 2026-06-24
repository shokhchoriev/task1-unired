# Add-card conversation states
CARD_NUMBER, CARD_EXPIRY, CARD_PHONE, CARD_BALANCE = range(4)

# Transfer conversation states
TRF_SELECT_SENDER, TRF_RECEIVER, TRF_AMOUNT, TRF_CURRENCY, TRF_OTP = range(10, 15)

# Link existing card conversation states
LINK_CARD_NUMBER, LINK_CARD_EXPIRY = range(20, 22)

# Stripe payment conversation states
PAY_AMOUNT, PAY_CURRENCY = range(30, 32)

# Payment status conversation state
PAY_STATUS_EXT_ID = 40

# Refund conversation state
PAY_REFUND_EXT_ID = 50

# Tron send conversation states
TRON_RECV_ADDR, TRON_SEND_AMOUNT, TRON_CONFIRM = range(60, 63)

# TRX buy (Stripe → TRX) conversation state
TRX_BUY_AMOUNT = 70
