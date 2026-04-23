import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from jsonrpcserver import Error as RPCError
from jsonrpcserver import Result, Success, dispatch, method

from cards.models import Card

from .models import Error, Transfer
from .utils import FakeNotificationService, calculate_exchange, generate_otp


logger = logging.getLogger(__name__)
request_logger = logging.getLogger("task2.request")
error_logger = logging.getLogger("task2.error")

ERR_DUPLICATE_EXT_ID = 32701
ERR_INSUFFICIENT_BALANCE = 32702
ERR_INVALID_CURRENCY = 32703
ERR_NOT_FOUND = 32704
ERR_INVALID_AMOUNT = 32705
ERR_INVALID_STATE = 32708
ERR_INVALID_OTP = 32709
ERR_CANNOT_CANCEL = 32710
ERR_OTP_ATTEMPTS_EXCEEDED = 32711
ERR_INTERNAL = 32000


def get_custom_error(code):
    try:
        err_obj = Error.objects.get(code=code)
        return RPCError(code=err_obj.code, message=err_obj.en)
    except Error.DoesNotExist:
        return RPCError(code=code, message="Unknown error")


def _parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


@method
def transfer_create(
    ext_id,
    sender_card_number,
    sender_card_expiry,
    receiver_card_number,
    sending_amount,
    currency,
) -> Result:
    try:
        if Transfer.objects.filter(ext_id=ext_id).exists():
            return get_custom_error(ERR_DUPLICATE_EXT_ID)

        amount = _parse_amount(sending_amount)
        if amount is None:
            return get_custom_error(ERR_INVALID_AMOUNT)

        if currency not in {643, 840}:
            return get_custom_error(ERR_INVALID_CURRENCY)

        try:
            sender_card = Card.objects.get(card_number=sender_card_number, expire=sender_card_expiry)
            receiver_card = Card.objects.get(card_number=receiver_card_number)
        except Card.DoesNotExist:
            return get_custom_error(ERR_NOT_FOUND)

        if sender_card.balance < amount:
            return get_custom_error(ERR_INSUFFICIENT_BALANCE)

        receiving_amount = calculate_exchange(amount=amount, currency=currency)
        otp = generate_otp()
        transfer = Transfer.objects.create(
            ext_id=ext_id,
            sender_card_number=sender_card_number,
            receiver_card_number=receiver_card_number,
            sender_card_expiry=sender_card_expiry,
            sender_phone=sender_card.phone,
            receiver_phone=receiver_card.phone,
            sending_amount=amount,
            receiving_amount=receiving_amount,
            currency=currency,
            state=Transfer.State.CREATED,
            otp=otp,
        )

        FakeNotificationService().send_otp(
            phone=sender_card.phone,
            tg_id=getattr(sender_card, "tg_id", "unknown"),
            otp=otp,
        )
        return Success({"ext_id": ext_id, "state": transfer.state})
    except Exception:
        error_logger.exception("transfer_create failed: ext_id=%s", ext_id)
        return get_custom_error(ERR_INTERNAL)


@method
def transfer_confirm(ext_id, otp) -> Result:
    try:
        transfer = Transfer.objects.get(ext_id=ext_id)
    except Transfer.DoesNotExist:
        return get_custom_error(ERR_NOT_FOUND)

    if transfer.state != Transfer.State.CREATED:
        return get_custom_error(ERR_INVALID_STATE)

    if transfer.try_count >= 3:
        transfer.state = Transfer.State.CANCELLED
        transfer.cancelled_at = timezone.now()
        transfer.save(update_fields=["state", "cancelled_at", "updated_at"])
        return get_custom_error(ERR_OTP_ATTEMPTS_EXCEEDED)

    if transfer.otp != str(otp):
        transfer.try_count += 1
        update_fields = ["try_count", "updated_at"]
        if transfer.try_count >= 3:
            transfer.state = Transfer.State.CANCELLED
            transfer.cancelled_at = timezone.now()
            update_fields.extend(["state", "cancelled_at"])
            transfer.save(update_fields=update_fields)
            return get_custom_error(ERR_OTP_ATTEMPTS_EXCEEDED)

        transfer.save(update_fields=update_fields)
        return get_custom_error(ERR_INVALID_OTP)

    try:
        with transaction.atomic():
            sender_card = Card.objects.select_for_update().get(card_number=transfer.sender_card_number)
            receiver_card = Card.objects.select_for_update().get(card_number=transfer.receiver_card_number)

            if sender_card.balance < transfer.sending_amount:
                return get_custom_error(ERR_INSUFFICIENT_BALANCE)

            sender_card.balance -= transfer.sending_amount
            receiver_card.balance += transfer.receiving_amount
            sender_card.save(update_fields=["balance"])
            receiver_card.save(update_fields=["balance"])

            transfer.state = Transfer.State.CONFIRMED
            transfer.confirmed_at = timezone.now()
            transfer.save(update_fields=["state", "confirmed_at", "updated_at"])
    except Card.DoesNotExist:
        return get_custom_error(ERR_NOT_FOUND)
    except Exception:
        error_logger.exception("transfer_confirm failed: ext_id=%s", ext_id)
        return get_custom_error(ERR_INTERNAL)

    return Success({"ext_id": ext_id, "state": transfer.state})


@method
def transfer_cancel(ext_id) -> Result:
    try:
        transfer = Transfer.objects.get(ext_id=ext_id)
        if transfer.state == Transfer.State.CREATED:
            transfer.state = Transfer.State.CANCELLED
            transfer.cancelled_at = timezone.now()
            transfer.save(update_fields=["state", "cancelled_at", "updated_at"])
            return Success({"ext_id": ext_id, "state": transfer.state})
        return get_custom_error(ERR_CANNOT_CANCEL)
    except Transfer.DoesNotExist:
        return get_custom_error(ERR_NOT_FOUND)


@method
def transfer_state(ext_id) -> Result:
    try:
        transfer = Transfer.objects.get(ext_id=ext_id)
        return Success({"ext_id": ext_id, "state": transfer.state})
    except Transfer.DoesNotExist:
        return get_custom_error(ERR_NOT_FOUND)


@method
def transfer_history(card_number=None, status=None, date_from=None, date_to=None) -> Result:
    queryset = Transfer.objects.all()

    if card_number:
        queryset = queryset.filter(sender_card_number=card_number)
    if status:
        queryset = queryset.filter(state=status)
    if date_from:
        queryset = queryset.filter(created_at__gte=datetime.fromisoformat(date_from))
    if date_to:
        filters['created_at_lte'] = datetime.fromisoformat(date_to)

    transfers = Transfer.objects.filter(**filters)
    data = [{"ext_id": t.ext_id, "amount": str(t.sending_amount), "state": t.state, "date": t.created_at.isoformat()} for t in transfers]
    return Success(data)




@csrf_exempt
def json_rpc_view(request):
    request_data = request.body.decode("utf-8")
    logger.info(f"Request: {request_data}")
    
    response = dispatch(request_data)
    
    logger.info(f"Response: {response}")
    return JsonResponse(response, safe=False)
