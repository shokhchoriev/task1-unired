import json
from unittest.mock import MagicMock, patch

import stripe
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Payment


# ─── GET /task2/payment/status/ ───────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=["*"])
class PaymentStatusAPITest(TestCase):
    def setUp(self):
        self.payment = Payment.objects.create(
            ext_id="test_ext_12345",
            card_number_hash="abc123hash",
            amount="150.00",
            currency="UZS",
            provider=Payment.Provider.PAYME,
            status=Payment.Status.SUCCESS,
        )
        self.url = reverse("payment_status")

    def test_status_success_200(self):
        response = self.client.get(self.url, {"ext_id": self.payment.ext_id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["amount"], "150.00")
        self.assertEqual(data["ext_id"], "test_ext_12345")

    def test_status_missing_ext_id_returns_400(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("ext_id is required", response.json()["message"])

    def test_status_not_found_returns_404(self):
        response = self.client.get(self.url, {"ext_id": "nonexistent_id_999"})
        self.assertEqual(response.status_code, 404)
        self.assertIn("Payment topilmadi", response.json()["error"])

    def test_status_response_contains_all_fields(self):
        response = self.client.get(self.url, {"ext_id": self.payment.ext_id})
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("ext_id", data)
        self.assertIn("amount", data)
        self.assertIn("status", data)

    def test_status_pending_payment(self):
        pending = Payment.objects.create(
            ext_id="pending_ext_001",
            card_number_hash="def456hash",
            amount="500.00",
            currency="USD",
            provider=Payment.Provider.STRIPE,
            status=Payment.Status.PENDING,
        )
        response = self.client.get(self.url, {"ext_id": pending.ext_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")


# ─── POST /pay/ ───────────────────────────────────────────────────────────────

@override_settings(
    ALLOWED_HOSTS=["*"],
    STRIPE_SECRET_KEY="sk_test_fake",
    SIGNATURE_EXEMPT_PATHS=["/admin/", "/stripe/webhook/", "/pay/"],
)
class PayAPITest(TestCase):
    VALID_PAYLOAD = {
        "card_number": "4242424242424242",
        "expire": "12/26",
        "amount": "10.00",
        "currency": "USD",
        "provider": "stripe",
    }

    def _post(self, data):
        return self.client.post(
            reverse("pay"),
            data=json.dumps(data),
            content_type="application/json",
        )

    def _make_mocks(self, intent_status="succeeded"):
        pm = MagicMock()
        pm.id = "pm_test_123"
        intent = MagicMock()
        intent.id = "pi_test_123"
        intent.status = intent_status
        return pm, intent

    @patch("payments.services.stripe.PaymentIntent.create")
    @patch("payments.services.stripe.PaymentMethod.create")
    def test_pay_stripe_success_returns_200(self, mock_pm, mock_intent):
        pm, intent = self._make_mocks("succeeded")
        mock_pm.return_value = pm
        mock_intent.return_value = intent

        resp = self._post(self.VALID_PAYLOAD)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["provider_transaction_id"], "pi_test_123")
        self.assertIn("ext_id", data)

    @patch("payments.services.stripe.PaymentIntent.create")
    @patch("payments.services.stripe.PaymentMethod.create")
    def test_pay_stripe_failure_returns_402(self, mock_pm, mock_intent):
        pm, intent = self._make_mocks("requires_payment_method")
        mock_pm.return_value = pm
        mock_intent.return_value = intent

        resp = self._post(self.VALID_PAYLOAD)

        self.assertEqual(resp.status_code, 402)
        self.assertEqual(resp.json()["status"], "failed")

    def test_pay_invalid_card_number_returns_400(self):
        payload = {**self.VALID_PAYLOAD, "card_number": "123"}
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("errors", resp.json())

    def test_pay_missing_required_field_returns_400(self):
        payload = {k: v for k, v in self.VALID_PAYLOAD.items() if k != "amount"}
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)


# ─── POST /stripe/webhook/ ────────────────────────────────────────────────────

@override_settings(
    ALLOWED_HOSTS=["*"],
    STRIPE_WEBHOOK_SECRET="whsec_test_secret_123",
)
class StripeWebhookAPITest(TestCase):
    def setUp(self):
        self.url = reverse("stripe_webhook")
        self.payment = Payment.objects.create(
            ext_id="wh-test-001",
            card_number_hash="hash_wh_001",
            amount="20.00",
            currency="USD",
            provider=Payment.Provider.STRIPE,
            status=Payment.Status.PENDING,
            provider_transaction_id="pi_webhook_test",
        )

    def _post(self, body=b'{"type":"test"}', sig="test_sig"):
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )

    def _succeeded_event(self, intent_id="pi_webhook_test"):
        return {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": intent_id}},
        }

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_valid_signature_succeeded_updates_payment(self, mock_construct):
        mock_construct.return_value = self._succeeded_event()

        resp = self._post()

        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_invalid_signature_returns_400(self, mock_construct):
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "bad_sig"
        )

        resp = self._post()

        self.assertEqual(resp.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_malformed_payload_returns_400(self, mock_construct):
        mock_construct.side_effect = ValueError("No JSON object")

        resp = self._post()

        self.assertEqual(resp.status_code, 400)

    def test_missing_webhook_secret_returns_400(self):
        with self.settings(STRIPE_WEBHOOK_SECRET=""):
            resp = self._post()
        self.assertEqual(resp.status_code, 400)

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_idempotency_second_delivery_is_noop(self, mock_construct):
        mock_construct.return_value = self._succeeded_event()

        # First delivery — updates PENDING → SUCCESS
        resp1 = self._post()
        self.assertEqual(resp1.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

        # Record updated_at after first real save
        updated_at_after_first = self.payment.updated_at

        # Second delivery of the same event — status already SUCCESS, must skip save
        resp2 = self._post()
        self.assertEqual(resp2.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)
        self.assertEqual(self.payment.updated_at, updated_at_after_first)


# ─── POST /stripe/refund/ ─────────────────────────────────────────────────────

@override_settings(
    ALLOWED_HOSTS=["*"],
    STRIPE_SECRET_KEY="sk_test_fake",
    SIGNATURE_EXEMPT_PATHS=["/admin/", "/stripe/webhook/", "/stripe/refund/"],
)
class StripeRefundAPITest(TestCase):
    def setUp(self):
        self.url = reverse("stripe_refund")
        self.payment = Payment.objects.create(
            ext_id="refund-test-001",
            card_number_hash="hash_ref_001",
            amount="50.00",
            currency="USD",
            provider=Payment.Provider.STRIPE,
            status=Payment.Status.SUCCESS,
            provider_transaction_id="pi_refund_test",
        )

    def _post(self, ext_id):
        return self.client.post(
            self.url,
            data=json.dumps({"ext_id": ext_id}),
            content_type="application/json",
        )

    @patch("payments.services.stripe.Refund.create")
    def test_refund_success_returns_200(self, mock_refund_create):
        mock_ref = MagicMock()
        mock_ref.id = "re_test_success_001"
        mock_refund_create.return_value = mock_ref

        resp = self._post("refund-test-001")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["refund_id"], "re_test_success_001")
        self.assertEqual(data["status"], "refunded")
        self.assertEqual(data["ext_id"], "refund-test-001")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.REFUNDED)
        self.assertEqual(self.payment.refund_id, "re_test_success_001")

    def test_refund_already_refunded_returns_409(self):
        self.payment.status = Payment.Status.REFUNDED
        self.payment.refund_id = "re_existing"
        self.payment.save()

        resp = self._post("refund-test-001")

        self.assertEqual(resp.status_code, 409)
        self.assertIn("already refunded", resp.json()["error"])

    def test_refund_not_found_returns_404(self):
        resp = self._post("does-not-exist")
        self.assertEqual(resp.status_code, 404)
