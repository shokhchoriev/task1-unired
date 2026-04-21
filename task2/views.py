import logging
import random
from decimal import Decimal
from datetime import datetime
from jsonrpcserver import method, dispatch, Success, Result, Error as RPCError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from cards.models import Card
from .models import Transfer, Error


logger = logging.getLogger(__name__)

def get_custom_error(code):
    try:
        err_obj = Error.objects.get(code=code)
        return RPCError(code=err_obj.code, message=err_obj.en)
    except Error.DoesNotExist:
        return RPCError(code=code, message="Unknown error")

@method
def transfer_create(ext_id, sender_card_number, sender_card_expiry,
                    receiver_card_number, sending_amount, currency) -> Result:
    try:

        if Transfer.objects.filter(ext_id=ext_id).exists():
            return get_custom_error(32701)


        try:
            sender_card = Card.objects.get(card_number=sender_card_number, expire=sender_card_expiry)
            receiver_card = Card.objects.get(card_number=receiver_card_number)
        except Card.DoesNotExist:
            return get_custom_error(32704)

        if sender_card.balance < Decimal(sending_amount):
            return get_custom_error(32702)


        otp = str(random.randint(100000, 999999))
        transfer = Transfer.objects.create(
            ext_id=ext_id, sender_card_number=sender_card_number,
            receiver_card_number=receiver_card_number,
            sending_amount=sending_amount, currency=currency,
            state=Transfer.CREATED, otp=otp
        )
        
        print(f"OTP sent to {sender_card.phone}: {otp}") 
        return Success({"ext_id": ext_id, "state": transfer.state})

    except Exception as e:
        logger.error(f"Create error: {str(e)}")
        return get_custom_error(32000)

@method
def transfer_confirm(ext_id, otp) -> Result:
    try:
        transfer = Transfer.objects.get(ext_id=ext_id)
        
        if transfer.state != Transfer.CREATED:
            return get_custom_error(32708)

        transfer.try_count += 1
        if transfer.otp != otp:
            transfer.save()
            return get_custom_error(32709)

        transfer.state = Transfer.CONFIRMED
        transfer.save()
        return Success({"ext_id": ext_id, "state": transfer.state})
    except Transfer.DoesNotExist:
        return get_custom_error(32704)

@method
def transfer_cancel(ext_id) -> Result:
    try:
        transfer = Transfer.objects.get(ext_id=ext_id)
        if transfer.state == Transfer.CREATED:
            transfer.state = Transfer.CANCELLED
            transfer.save()
            return Success({"ext_id": ext_id, "state": transfer.state})
        return get_custom_error(32710)
    except Transfer.DoesNotExist:
        return get_custom_error(32704)

@method
def transfer_state(ext_id) -> Result:
    try:
        transfer = Transfer.objects.get(ext_id=ext_id)
        return Success({"ext_id": ext_id, "state": transfer.state})
    except Transfer.DoesNotExist:
        return get_custom_error(32704)

@method
def transfer_history(card_number=None, status=None, date_from=None, date_to=None) -> Result:
    filters = {}
    if card_number: filters['sender_card_number'] = card_number
    if status: filters['state'] = status

    
    transfers = Transfer.objects.filter(**filters)
    data = [{"ext_id": t.ext_id, "amount": str(t.sending_amount), "state": t.state} for t in transfers]
    return Success(data)

@csrf_exempt
def json_rpc_view(request):
    request_data = request.body.decode("utf-8")
    logger.info(f"Request: {request_data}")
    
    response = dispatch(request_data)
    
    logger.info(f"Response: {response}")
    return JsonResponse(response, safe=False)
