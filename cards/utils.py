import re

def normalize_phone(phone):
    if not phone:
        return None
    phone = re.sub(r'\D', '', phone)
    if phone.startswith('998'):
        return '+' + phone
    return phone

def normalize_card_number(card_number):
    return re.sub(r'\s+', '', card_number)