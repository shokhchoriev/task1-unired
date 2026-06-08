from rest_framework import serializers
CARD_NUMBER_REGEX = r"^\d{16}$"
DATE_REGEX = r"^\d{4}-\d{2}-\d{2}$"
OTP_REGEX = r"^\d{4,8}$"
class TransferCreateSerializer(serializers.Serializer):
    """Validates ``transfer.create`` JSON-RPC params before they reach the handler.

    Only checks structural integrity (required fields, types, lengths, the
    16-digit card format) — semantic checks that already map to dedicated RPC
    error codes downstream (currency allow-list -> 32707, expiry validity ->
    32704, amount sign -> 32709) are intentionally left to the handler so the
    documented error contract doesn't change.
    """

    ext_id = serializers.CharField(max_length=100, allow_blank=False)
    sender_card_number = serializers.RegexField(CARD_NUMBER_REGEX)
    sender_card_expiry = serializers.CharField(max_length=10, allow_blank=False)
    receiver_card_number = serializers.RegexField(CARD_NUMBER_REGEX)
    sending_amount = serializers.CharField(max_length=32, allow_blank=False)
    currency = serializers.IntegerField()


class TransferConfirmSerializer(serializers.Serializer):
    """Validates ``transfer.confirm`` JSON-RPC params (ext_id + 6-digit OTP)."""

    ext_id = serializers.CharField(max_length=100, allow_blank=False)
    otp = serializers.RegexField(OTP_REGEX)


class ExtIdSerializer(serializers.Serializer):
    """Validates params for ``transfer.cancel`` / ``transfer.state`` (ext_id only)."""

    ext_id = serializers.CharField(max_length=100, allow_blank=False)


class TransferHistorySerializer(serializers.Serializer):
    """Validates optional filters for ``transfer.history``."""

    card_number = serializers.RegexField(
        CARD_NUMBER_REGEX, required=False, allow_null=True
    )
    start_date = serializers.RegexField(DATE_REGEX, required=False, allow_null=True)
    end_date = serializers.RegexField(DATE_REGEX, required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=["created", "confirmed", "cancelled"],
        required=False,
        allow_null=True,
    )


class CardInfoSerializer(serializers.Serializer):
    """Validates ``card.info`` JSON-RPC params (card_number + expiry).

    ``expiry`` is only checked structurally (non-blank string) — format
    validity is the handler's job and already maps to RPCError 32704.
    """

    card_number = serializers.RegexField(CARD_NUMBER_REGEX)
    expiry = serializers.CharField(max_length=10, allow_blank=False)
