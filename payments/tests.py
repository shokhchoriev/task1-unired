from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Payment


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
