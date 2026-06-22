from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .models import Payment


@override_settings(ALLOWED_HOSTS=['*'], DEBUG=False)
class PaymentStatusAPITest(TestCase):
    def setUp(self):
        self.payment = Payment.objects.create(
            amount=150.00,
            status='success',
            ext_id='test_ext_12345'
        )

        self.url = reverse('payment_status')

    def test_status_success_200(self):
        response = self.client.get(self.url, {"ext_id": self.payment.ext_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['amount'], '150.00')

    def test_status_missing_ext_id_400(self):
        """Проверка ответа 400, если ext_id не передан"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertIn('ext_id is required', response.json()['message'])

    def test_status_not_found_404(self):
        """Проверка ответа 404, если платеж не существует"""
        response = self.client.get(self.url, {'ext_id': 'invalid_id_999'})

        self.assertEqual(response.status_code, 404)
        self.assertIn('Payment topilmadi', response.json()['error'])