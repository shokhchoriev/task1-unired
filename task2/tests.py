import json
from decimal import Decimal

from django.core.management import call_command
from django.test import Client, TestCase

from cards.models import Card

from .models import Transfer
from .views import transfer_confirm, transfer_create


class TransferRPCUnitTests(TestCase):
    def setUp(self):
        call_command("populate_errors")
        self.sender = Card.objects.create(
            tg_id="10001",
            card_number="8600123412341234",
            expire="2024-12",
            phone="+998901112233",
            status="active",
            balance=Decimal("100000.00"),
        )
        self.receiver = Card.objects.create(
            tg_id="10002",
            card_number="8600567856785678",
            expire="2025-11",
            phone="+998909998877",
            status="active",
            balance=Decimal("1000.00"),
        )

    def _assert_success(self, rpc_result):
        self.assertTrue(hasattr(rpc_result, "_value"))
        return rpc_result._value.result

    def _assert_error(self, rpc_result, expected_code):
        self.assertTrue(hasattr(rpc_result, "_error"))
        self.assertEqual(rpc_result._error.code, expected_code)
        return rpc_result._error

    def test_transfer_create(self):
        rpc_result = transfer_create(
            ext_id="ext-create-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry=self.sender.expire,
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        payload = self._assert_success(rpc_result)

        transfer = Transfer.objects.get(ext_id="ext-create-1")
        self.assertEqual(payload["state"], Transfer.State.CREATED)
        self.assertEqual(transfer.state, Transfer.State.CREATED)
        self.assertEqual(transfer.sender_phone, self.sender.phone)
        self.assertEqual(transfer.receiver_phone, self.receiver.phone)
        self.assertEqual(len(transfer.otp), 6)

    def test_transfer_confirm(self):
        transfer_create(
            ext_id="ext-confirm-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry=self.sender.expire,
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        transfer = Transfer.objects.get(ext_id="ext-confirm-1")

        rpc_result = transfer_confirm(ext_id=transfer.ext_id, otp=transfer.otp)
        payload = self._assert_success(rpc_result)

        transfer.refresh_from_db()
        self.sender.refresh_from_db()
        self.receiver.refresh_from_db()

        self.assertEqual(payload["state"], Transfer.State.CONFIRMED)
        self.assertEqual(transfer.state, Transfer.State.CONFIRMED)
        self.assertIsNotNone(transfer.confirmed_at)
        self.assertEqual(self.sender.balance, Decimal("99990.00"))
        self.assertEqual(self.receiver.balance, Decimal("2400.00"))

    def test_otp_error(self):
        transfer_create(
            ext_id="ext-otp-1",
            sender_card_number=self.sender.card_number,
            sender_card_expiry=self.sender.expire,
            receiver_card_number=self.receiver.card_number,
            sending_amount="10.00",
            currency=643,
        )
        transfer = Transfer.objects.get(ext_id="ext-otp-1")

        first_try = transfer_confirm(ext_id=transfer.ext_id, otp="000000")
        self._assert_error(first_try, 32709)
        transfer.refresh_from_db()
        self.assertEqual(transfer.try_count, 1)
        self.assertEqual(transfer.state, Transfer.State.CREATED)

        second_try = transfer_confirm(ext_id=transfer.ext_id, otp="111111")
        self._assert_error(second_try, 32709)
        transfer.refresh_from_db()
        self.assertEqual(transfer.try_count, 2)
        self.assertEqual(transfer.state, Transfer.State.CREATED)

        third_try = transfer_confirm(ext_id=transfer.ext_id, otp="222222")
        self._assert_error(third_try, 32711)
        transfer.refresh_from_db()
        self.assertEqual(transfer.try_count, 3)
        self.assertEqual(transfer.state, Transfer.State.CANCELLED)
        self.assertIsNotNone(transfer.cancelled_at)


class TransferRPCIntegrationTests(TestCase):
    def setUp(self):
        call_command("populate_errors")
        self.client = Client()
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
        self.url = "/task2/api/v1/rpc/"

    def _rpc(self, method, params, request_id=1):
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_full_flow_create_confirm_state(self):
        create_response = self._rpc(
            method="transfer_create",
            params={
                "ext_id": "ext-int-1",
                "sender_card_number": self.sender.card_number,
                "sender_card_expiry": self.sender.expire,
                "receiver_card_number": self.receiver.card_number,
                "sending_amount": "3.00",
                "currency": 643,
            },
            request_id=11,
        )
        self.assertIn("result", create_response)
        self.assertEqual(create_response["result"]["state"], Transfer.State.CREATED)

        transfer = Transfer.objects.get(ext_id="ext-int-1")
        confirm_response = self._rpc(
            method="transfer_confirm",
            params={"ext_id": "ext-int-1", "otp": transfer.otp},
            request_id=12,
        )
        self.assertIn("result", confirm_response)
        self.assertEqual(confirm_response["result"]["state"], Transfer.State.CONFIRMED)

        state_response = self._rpc(
            method="transfer_state",
            params={"ext_id": "ext-int-1"},
            request_id=13,
        )
        self.assertIn("result", state_response)
        self.assertEqual(state_response["result"]["state"], Transfer.State.CONFIRMED)
