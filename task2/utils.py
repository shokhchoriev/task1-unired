import random
from .models import Transfer

def generate_otp(length=6):
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def send_telegram_message(phone, message, chat_id=123456):
    print(f"[TELEGRAM] To: {phone}")
    print(f"Message: {message}")
    return True

def validate_card(card_number):
    card_number = card_number.replace(" ", "")
    
    if not card_number.isdigit():
        return False

    total = 0
    reverse_digits = card_number[::-1]

    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0

def check_balance(card, amount):
    return card.balance >= amount

def calculate_exchange(amount, currency):
    rates = {
        643: 140,  #rubli > sumga otqizdim 
        840: 12500  #dollari > somga otiqizdim 
    }

    if currency not in rates:
        raise Exception("Currency not allowed")

    return amount * rates[currency]


def get_transfer_by_ext_id(ext_id):
    try:
        return Transfer.objects.get(ext_id=ext_id)
    except Transfer.DoesNotExist:
        return None
    
def check_otp(transfer, otp):
    if transfer.try_count >= 3:
        raise Exception("Urinishlar soni tugagan")

    if transfer.otp != otp:
        transfer.try_count += 1
        transfer.save()
        raise Exception(f"Noto‘g‘ri OTP, yana {3 - transfer.try_count} urinish qoldi")

    return True