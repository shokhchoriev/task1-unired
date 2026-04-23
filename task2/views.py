import random
from decimal import Decimal
from datetime import datetime
from jsonrpcserver import method, dispatch
from django.http import JsonResponse
from cards.models import Card
from .models import Transfer, Error


def send_otp_via_telegram(phone, otp):
    print(f"Sending OTP {otp} to phone {phone}")
    return True


@method
def transfer_create(ext_id, sender_card_number, sender_card_expiry,
                    receiver_card_number, sending_amount, currency):
    

    if Transfer.objects.filter(ext_id=ext_id).exists():
        error = Error.objects.get(code=32701)
        return {"error": {"code": error.code, "message": error.en}}


    try:
        sender_card = Card.objects.get(card_number=sender_card_number,
                                       expire=sender_card_expiry)
    except Card.DoesNotExist:
        error = Error.objects.get(code=32704)
        return {"error": {"code": error.code, "message": error.en}}

    if sender_card.status != "active":
        error = Error.objects.get(code=32705)
        return {"error": {"code": error.code, "message": error.en}}

    if sender_card.balance < Decimal(sending_amount):
        error = Error.objects.get(code=32702)
        return {"error": {"code": error.code, "message": error.en}}


    try:
        receiver_card = Card.objects.get(card_number=receiver_card_number)
    except Card.DoesNotExist:
        error = Error.objects.get(code=32704)
        return {"error": {"code": error.code, "message": error.en}}


    if currency not in [643, 840]:
        error = Error.objects.get(code=32707)
        return {"error": {"code": error.code, "message": error.en}}


    otp = f"{random.randint(100000, 999999)}"


    transfer = Transfer.objects.create(
        ext_id=ext_id,
        sender_card_number=sender_card_number,
        sender_card_expiry=sender_card_expiry,
        receiver_card_number=receiver_card_number,
        sending_amount=sending_amount,
        currency=currency,
        receiving_amount=sending_amount,
        state=Transfer.CREATED,
        otp=otp,
        try_count=0
    )


    otp_sent = send_otp_via_telegram(sender_card.sender_phone, otp)

    return {
        "ext_id": transfer.ext_id,
        "state": transfer.state,
        "otp_sent": otp_sent
    }

from django.views.decorators.csrf import csrf_exempt

def json_rpc_view(request):
    request_data = request.body.decode("utf-8")
    response = dispatch(request_data)
    return JsonResponse(response, safe=False)
