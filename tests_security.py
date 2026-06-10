import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from dotenv import dotenv_values

from config.helpers import mask_card_number, mask_otp
from config.security import generate_hash

User = get_user_model()


BASE_DIR = Path(__file__).resolve().parent
ENV_VALUES = dotenv_values(BASE_DIR / ".env")
EXPECTED_CORS_ALLOWED_ORIGINS = {
    "https://yourfrontend.com",
    "http://localhost:3000",
}
JSON_RPC_ENDPOINT = "/task2/"


class SecurityConfigurationTests(SimpleTestCase):
    """Automated checks for tasks 5.1, 5.5, and 5.6."""

    def log_ok(self, message):
        print(f"LOG: {message} [OK]")

    def test_environment_variables_loaded_and_not_empty(self):
        """5.6: Required secrets/config values must come from environment."""
        required_values = {
            "SECRET_KEY": getattr(settings, "SECRET_KEY", ""),
            "DEBUG": str(getattr(settings, "DEBUG", "")),
            "ALLOWED_HOSTS": ",".join(getattr(settings, "ALLOWED_HOSTS", [])),
            "TELEGRAM_BOT_TOKEN": getattr(settings, "TELEGRAM_BOT_TOKEN", ""),
            "ENCRYPTION_KEY": getattr(settings, "ENCRYPTION_KEY", ""),
        }

        missing_env_keys = [
            key
            for key in required_values
            if key not in ENV_VALUES and not (key == "SECRET_KEY" and "DJANGO_SECRET_KEY" in ENV_VALUES)
        ]
        empty_values = [key for key, value in required_values.items() if not str(value).strip()]

        self.assertEqual(
            missing_env_keys,
            [],
            f".env faylida quyidagi kalitlar yo'q: {missing_env_keys}",
        )
        self.assertEqual(
            empty_values,
            [],
            f"Quyidagi environment qiymatlar bo'sh: {empty_values}",
        )

        self.log_ok("Environment variables testi muvaffaqiyatli o'tdi")

    def test_cors_settings_allow_only_trusted_origins(self):
        """5.1: CORS must be locked to a small trusted allowlist."""
        self.assertFalse(
            getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False),
            "CORS_ALLOW_ALL_ORIGINS production muhitida True bo'lmasligi kerak.",
        )
        self.assertEqual(
            set(settings.CORS_ALLOWED_ORIGINS),
            EXPECTED_CORS_ALLOWED_ORIGINS,
            "CORS_ALLOWED_ORIGINS faqat ishonchli domenlardan iborat bo'lishi kerak.",
        )

        self.log_ok("CORS settings testi muvaffaqiyatli o'tdi")

    def test_cors_preflight_headers_for_allowed_and_blocked_origins(self):
        """5.1: OPTIONS preflight must return CORS headers only for trusted origins."""
        client = Client()

        allowed_response = client.options(
            JSON_RPC_ENDPOINT,
            HTTP_ORIGIN="https://yourfrontend.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(
            allowed_response.headers.get("Access-Control-Allow-Origin"),
            "https://yourfrontend.com",
            "Ruxsat berilgan origin uchun Access-Control-Allow-Origin qaytishi kerak.",
        )

        blocked_response = client.options(
            JSON_RPC_ENDPOINT,
            HTTP_ORIGIN="https://hacker.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertNotIn(
            "Access-Control-Allow-Origin",
            blocked_response.headers,
            "Begona origin uchun Access-Control-Allow-Origin qaytmasligi kerak.",
        )

        self.log_ok("CORS preflight testi muvaffaqiyatli o'tdi")

    def test_debug_and_production_safety_settings(self):
        """5.5: Production safety switches must be strict."""
        self.assertIs(
            settings.DEBUG,
            False,
            "DEBUG production xavfsizligi uchun mutlaqo False bo'lishi kerak.",
        )
        self.assertTrue(
            settings.ALLOWED_HOSTS,
            "ALLOWED_HOSTS bo'sh bo'lmasligi kerak.",
        )

        self.log_ok("Debug va production safety testi muvaffaqiyatli o'tdi")

    def test_sensitive_data_masking_helpers(self):
        """5.5: Card numbers and OTP values must be masked before logging."""
        self.assertEqual(
            mask_card_number("8600123412341234"),
            "860012******1234",
            "Karta raqami noto'g'ri mask qilindi.",
        )
        self.assertEqual(
            mask_otp("12345"),
            "*****",
            "OTP kodi noto'g'ri mask qilindi.",
        )

        self.log_ok("Masking helperlari testi muvaffaqiyatli o'tdi")


class RequestSignatureTests(TestCase):
    """5.3: HMAC-SHA256 request signing middleware."""

    RPC_URL = "/task2/"

    def setUp(self):
        self.user = User.objects.create_user(username="sigtest", password="testpass123")
        # UserProfile auto-created by post_save signal; fetch the secret
        self.secret = self.user.userprofile.secret
        self.client.login(username="sigtest", password="testpass123")
        self.body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "transfer.state",
                "params": {"ext_id": "nonexistent-ext-id"},
            }
        ).encode()

    def test_wrong_signature_returns_403(self):
        """A request with an incorrect request-sign header must be rejected."""
        response = self.client.post(
            self.RPC_URL,
            data=self.body,
            content_type="application/json",
            HTTP_REQUEST_SIGN="deadbeefdeadbeefdeadbeefdeadbeef",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.json())

    def test_missing_signature_returns_403(self):
        """A request with no request-sign header must be rejected."""
        response = self.client.post(
            self.RPC_URL,
            data=self.body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Missing signature")

    def test_correct_signature_passes(self):
        """A request signed with the user's secret must not be rejected by the middleware."""
        correct_sign = generate_hash(self.body.decode(), self.secret)
        response = self.client.post(
            self.RPC_URL,
            data=self.body,
            content_type="application/json",
            HTTP_REQUEST_SIGN=correct_sign,
        )
        self.assertNotEqual(response.status_code, 403)
