import json
from decimal import Decimal

from django.core.management import call_command
from django.test import Client, TestCase

from cards.models import Card

from .models import Transfer
from .views import transfer_confirm, transfer_create


class TransferRPCUnitTests(TestCase):
    """Direct function-call tests (bypass HTTP layer)."""

    def setUp(self):
        call_command("populate_errors", verbosity=0)
        self.sender = Card.objects.create(
            tg_id="10001",
            card_number="8600123412341234",
            expire="2026-12",
            phone="+998901112233",
            status="active",
            balance=Decimal("100000.00"),
        )
        self.receiver = Card.objects.create(
            tg_id="10002",
            card_number="8600567856785678",
            expire="2027-11",
            phone="+998909998877",
            status="active",
            balance=Decimal("1000.00"),
        )

    def _assert_success(self, rpc_result):
        self.assertTrue(hasattr(rpc_result, "_value"), "Expected Success result but got Error")
        return rpc_result._value.result

    def _assert_error(self, rpc_result, expected_code):
        self.assertTrue(hasattr(rpc_result, "_error"), "Expected Error result but got Success")
        self.assertEqual(rpc_result._error.code, expected_code)
        return rpc_result._error

    # ------------------------------------------------------------------
    # transfer.create
    # ------------------------------------------------------------------

    def test_transfer_create_success(self):
        result = transfer_create(
            ext_id="ext-create-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        payload = self._assert_success(result)

        transfer = Transfer.objects.get(ext_id="ext-create-1")
        self.assertEqual(payload["state"], Transfer.State.CREATED)
        self.assertTrue(payload["otp_sent"])
        self.assertEqual(transfer.state, Transfer.State.CREATED)
        self.assertEqual(transfer.sender_phone, self.sender.phone)
        self.assertEqual(transfer.receiver_phone, self.receiver.phone)
        self.assertEqual(len(transfer.otp), 6)

    def test_transfer_create_duplicate_ext_id(self):
        transfer_create(
            ext_id="ext-dup-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        result = transfer_create(
            ext_id="ext-dup-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        self._assert_error(result, 32701)

    def test_transfer_create_invalid_currency(self):
        result = transfer_create(
            ext_id="ext-cur-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=999,
        )
        self._assert_error(result, 32707)

    def test_transfer_create_invalid_expiry(self):
        result = transfer_create(
            ext_id="ext-exp-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="99/99",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        self._assert_error(result, 32706)

    def test_transfer_create_insufficient_balance(self):
        result = transfer_create(
            ext_id="ext-bal-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="999999.00",
            currency=643,
        )
        self._assert_error(result, 32702)

    def test_transfer_create_inactive_card(self):
        self.sender.status = "inactive"
        self.sender.save(update_fields=["status"])
        result = transfer_create(
            ext_id="ext-act-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        self._assert_error(result, 32705)

    # ------------------------------------------------------------------
    # transfer.confirm
    # ------------------------------------------------------------------

    def test_transfer_confirm_success(self):
        transfer_create(
            ext_id="ext-confirm-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        transfer = Transfer.objects.get(ext_id="ext-confirm-1")

        result = transfer_confirm(ext_id=transfer.ext_id, otp=transfer.otp)
        payload = self._assert_success(result)

        transfer.refresh_from_db()
        self.sender.refresh_from_db()
        self.receiver.refresh_from_db()

        self.assertEqual(payload["state"], Transfer.State.CONFIRMED)
        self.assertEqual(transfer.state, Transfer.State.CONFIRMED)
        self.assertIsNotNone(transfer.confirmed_at)
        # Both sides use the real CBU rate stored in transfer.receiving_amount
        received = transfer.receiving_amount
        self.assertEqual(self.sender.balance, Decimal("100000.00") - received)
        self.assertEqual(self.receiver.balance, Decimal("1000.00") + received)

    def test_transfer_confirm_wrong_otp_increments_try_count(self):
        transfer_create(
            ext_id="ext-otp-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        transfer = Transfer.objects.get(ext_id="ext-otp-1")

        first_try = transfer_confirm(ext_id=transfer.ext_id, otp="000000")
        self._assert_error(first_try, 32712)
        transfer.refresh_from_db()
        self.assertEqual(transfer.try_count, 1)
        self.assertEqual(transfer.state, Transfer.State.CREATED)

        second_try = transfer_confirm(ext_id=transfer.ext_id, otp="111111")
        self._assert_error(second_try, 32712)
        transfer.refresh_from_db()
        self.assertEqual(transfer.try_count, 2)
        self.assertEqual(transfer.state, Transfer.State.CREATED)

        third_try = transfer_confirm(ext_id=transfer.ext_id, otp="222222")
        self._assert_error(third_try, 32711)
        transfer.refresh_from_db()
        self.assertEqual(transfer.try_count, 3)
        self.assertEqual(transfer.state, Transfer.State.CANCELLED)
        self.assertIsNotNone(transfer.cancelled_at)

    # ------------------------------------------------------------------
    # transfer.cancel / transfer.state
    # ------------------------------------------------------------------

    def test_transfer_cancel_success(self):
        transfer_create(
            ext_id="ext-cancel-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        from .views import transfer_cancel

        result = transfer_cancel(ext_id="ext-cancel-1")
        payload = self._assert_success(result)
        self.assertEqual(payload["state"], Transfer.State.CANCELLED)

    def test_transfer_state(self):
        transfer_create(
            ext_id="ext-state-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry="12/26",
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        from .views import transfer_state

        result = transfer_state(ext_id="ext-state-1")
        payload = self._assert_success(result)
        self.assertEqual(payload["ext_id"], "ext-state-1")
        self.assertEqual(payload["state"], Transfer.State.CREATED)


class TransferRPCIntegrationTests(TestCase):
    """HTTP-level integration tests via Django test client."""

    def setUp(self):
        call_command("populate_errors", verbosity=0)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username="rpc_http_user", password="pass98765")
        self.client = Client()
        self.client.login(username="rpc_http_user", password="pass98765")
        self.secret = self.user.userprofile.secret
        self.sender = Card.objects.create(
            tg_id="30001",
            card_number="8600999911112222",
            expire="2026-06",
            phone="+998901234567",
            status="active",
            balance=Decimal("50000.00"),
        )
        self.receiver = Card.objects.create(
            tg_id="30002",
            card_number="8600888877776666",
            expire="2027-07",
            phone="+998907654321",
            status="active",
            balance=Decimal("0.00"),
        )
        self.url = "/task2/"

    def _rpc(self, method_name, params, request_id=1):
        from config.security import generate_hash
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method_name,
                "params": params,
            }
        )
        sign = generate_hash(body, self.secret)
        response = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_REQUEST_SIGN=sign,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_full_flow_create_confirm_state(self):
        create_response = self._rpc(
            method_name="transfer.create",
            params={
                "ext_id": "ext-int-1",
                "sender_card_number": self.sender.card_number,
                "sender_card_expiry": "06/26",
                "receiver_card_number": self.receiver.card_number,
                "sending_amount": "3.00",
                "currency": 643,
            },
            request_id=11,
        )
        self.assertIn("result", create_response)
        self.assertEqual(create_response["result"]["state"], Transfer.State.CREATED)
        self.assertTrue(create_response["result"]["otp_sent"])

        transfer = Transfer.objects.get(ext_id="ext-int-1")

        confirm_response = self._rpc(
            method_name="transfer.confirm",
            params={"ext_id": "ext-int-1", "otp": transfer.otp},
            request_id=12,
        )
        self.assertIn("result", confirm_response)
        self.assertEqual(confirm_response["result"]["state"], Transfer.State.CONFIRMED)

        state_response = self._rpc(
            method_name="transfer.state",
            params={"ext_id": "ext-int-1"},
            request_id=13,
        )
        self.assertIn("result", state_response)
        self.assertEqual(state_response["result"]["state"], Transfer.State.CONFIRMED)

    def test_cancel_flow(self):
        self._rpc(
            method_name="transfer.create",
            params={
                "ext_id": "ext-cancel-int-1",
                "sender_card_number": self.sender.card_number,
                "sender_card_expiry": "06/26",
                "receiver_card_number": self.receiver.card_number,
                "sending_amount": "3.00",
                "currency": 840,
            },
        )
        cancel_response = self._rpc(
            method_name="transfer.cancel",
            params={"ext_id": "ext-cancel-int-1"},
        )
        self.assertIn("result", cancel_response)
        self.assertEqual(cancel_response["result"]["state"], Transfer.State.CANCELLED)

    def test_history_filter_by_card(self):
        self._rpc(
            method_name="transfer.create",
            params={
                "ext_id": "ext-hist-1",
                "sender_card_number": self.sender.card_number,
                "sender_card_expiry": "06/26",
                "receiver_card_number": self.receiver.card_number,
                "sending_amount": "1.00",
                "currency": 643,
            },
        )
        history_response = self._rpc(
            method_name="transfer.history",
            params={"card_number": self.sender.card_number},
        )
        self.assertIn("result", history_response)
        self.assertEqual(len(history_response["result"]), 1)
        self.assertEqual(history_response["result"][0]["ext_id"], "ext-hist-1")

    def test_non_post_returns_405(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
