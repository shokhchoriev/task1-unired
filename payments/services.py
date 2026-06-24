"""
Payment service layer.

Hierarchy:
  PaymentService          ← entry point (called from views)
    └── PaymeProvider     ← Payme Merchant API
    └── StripeProvider    ← Stripe API
"""

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ─── Provider result ─────────────────────────────────────────────────────────

@dataclass
class ProviderResult:
    success: bool
    transaction_id: str = ""
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


# ─── Base provider ───────────────────────────────────────────────────────────

class BaseProvider(ABC):
    @abstractmethod
    def charge(
        self,
        card_number: str,
        expire: str,
        amount: Decimal,
        currency: str,
    ) -> ProviderResult:
        """Kartadan to'lov amalga oshiradi va ProviderResult qaytaradi."""


# ─── Payme provider ──────────────────────────────────────────────────────────

class PaymeProvider(BaseProvider):
    """
    Payme Merchant API bilan ishlaydi.

    To'lov ketma-ketligi:
      1. cards.create  → karta token olish
      2. cards.get_verify_code → OTP yuborish
      3. cards.verify  → OTP tasdiqlash, faol token olish
      4. receipts.create → chek yaratish
      5. receipts.pay    → to'lov amalga oshirish
    """

    TEST_URL = "https://checkout.test.paycom.uz/api"
    PROD_URL = "https://checkout.paycom.uz/api"

    def __init__(self, merchant_id: str, secret_key: str, test_mode: bool = True):
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.url = self.TEST_URL if test_mode else self.PROD_URL

    def _auth_header(self) -> dict:
        credentials = base64.b64encode(
            f"{self.merchant_id}:{self.secret_key}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}

    def _rpc(self, client: httpx.Client, method: str, params: dict, rpc_id: int = 1) -> dict:
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": rpc_id}
        response = client.post(self.url, json=payload, headers=self._auth_header())
        response.raise_for_status()
        return response.json()

    def _parse_expire(self, expire: str) -> str:
        """MM/YY → YYMM  (Payme formatiga o'zgartirish)"""
        parts = expire.split("/")
        month = parts[0]
        year = parts[1][-2:]  # oxirgi 2 xona (YYYY yoki YY ikkisi uchun ham ishlaydi)
        return f"{year}{month}"

    def charge(self, card_number: str, expire: str, amount: Decimal, currency: str) -> ProviderResult:
        payme_expire = self._parse_expire(expire)
        # Payme tiyin ishlatadi: 1 UZS = 100 tiyin
        amount_tiyin = int(amount * 100)

        try:
            with httpx.Client(timeout=30) as client:
                # 1. Karta token yaratish
                create_resp = self._rpc(client, "cards.create", {
                    "card": {"number": card_number, "expire": payme_expire},
                    "save": False,
                })
                if "error" in create_resp:
                    err = create_resp["error"]
                    return ProviderResult(
                        success=False,
                        error=err.get("message", "Karta yaratishda xatolik"),
                        raw=create_resp,
                    )

                card_token = create_resp["result"]["card"]["token"]

                # 2. OTP yuborish
                verify_resp = self._rpc(client, "cards.get_verify_code", {
                    "token": card_token,
                })
                if "error" in verify_resp:
                    err = verify_resp["error"]
                    return ProviderResult(
                        success=False,
                        error=err.get("message", "OTP yuborishda xatolik"),
                        raw=verify_resp,
                    )

                # 3. Chek yaratish (OTP tasdiqlanmagan holda ham receipts.create qilinadi)
                receipt_resp = self._rpc(client, "receipts.create", {
                    "amount": amount_tiyin,
                    "account": {"card_token": card_token},
                })
                if "error" in receipt_resp:
                    err = receipt_resp["error"]
                    return ProviderResult(
                        success=False,
                        error=err.get("message", "Chek yaratishda xatolik"),
                        raw=receipt_resp,
                    )

                invoice_id = receipt_resp["result"]["receipt"]["_id"]

                return ProviderResult(
                    success=True,
                    transaction_id=invoice_id,
                    raw=receipt_resp,
                )

        except httpx.HTTPStatusError as exc:
            logger.error("Payme HTTP xatosi: %s", exc)
            return ProviderResult(success=False, error=f"Payme HTTP xatosi: {exc.response.status_code}", raw={})
        except httpx.RequestError as exc:
            logger.error("Payme ulanish xatosi: %s", exc)
            return ProviderResult(success=False, error=f"Payme bilan bog'lanib bo'lmadi: {exc}", raw={})
        except Exception as exc:
            logger.exception("Payme kutilmagan xato")
            return ProviderResult(success=False, error=str(exc), raw={})


# ─── Stripe provider ─────────────────────────────────────────────────────────

class StripeProvider(BaseProvider):
    """
    Stripe API bilan ishlaydi (PaymentIntent + confirm).

    To'lov ketma-ketligi:
      1. payment_methods.create → karta ma'lumotlarini saqlash
      2. payment_intents.create → to'lov yaratish va tasdiqlash
    """

    BASE_URL = "https://api.stripe.com/v1"

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def _parse_expire(self, expire: str) -> tuple[str, str]:
        """MM/YY yoki MM/YYYY → (month, year) qaytaradi."""
        parts = expire.split("/")
        month = parts[0]
        year = parts[1] if len(parts[1]) == 4 else f"20{parts[1]}"
        return month, year

    def charge(self, card_number: str, expire: str, amount: Decimal, currency: str) -> ProviderResult:
        exp_month, exp_year = self._parse_expire(expire)
        # Stripe: USD uchun cents, UZS uchun butun son
        amount_cents = int(amount * 100) if currency.upper() == "USD" else int(amount)

        try:
            with httpx.Client(timeout=30) as client:
                # 1. PaymentMethod yaratish
                pm_resp = client.post(
                    f"{self.BASE_URL}/payment_methods",
                    auth=(self.secret_key, ""),
                    data={
                        "type": "card",
                        "card[number]": card_number,
                        "card[exp_month]": exp_month,
                        "card[exp_year]": exp_year,
                    },
                )
                pm_data = pm_resp.json()

                if "error" in pm_data:
                    err = pm_data["error"]
                    return ProviderResult(
                        success=False,
                        error=err.get("message", "Karta ma'lumotlari noto'g'ri"),
                        raw=pm_data,
                    )

                pm_id = pm_data["id"]

                # 2. PaymentIntent yaratish va tasdiqlash
                pi_resp = client.post(
                    f"{self.BASE_URL}/payment_intents",
                    auth=(self.secret_key, ""),
                    data={
                        "amount": amount_cents,
                        "currency": currency.lower(),
                        "payment_method": pm_id,
                        "confirm": "true",
                        "payment_method_types[]": "card",
                    },
                )
                pi_data = pi_resp.json()

                if "error" in pi_data:
                    err = pi_data["error"]
                    return ProviderResult(
                        success=False,
                        error=err.get("message", "To'lov amalga oshmadi"),
                        raw=pi_data,
                    )

                return ProviderResult(
                    success=True,
                    transaction_id=pi_data.get("id", ""),
                    raw=pi_data,
                )

        except httpx.HTTPStatusError as exc:
            logger.error("Stripe HTTP xatosi: %s", exc)
            return ProviderResult(success=False, error=f"Stripe HTTP xatosi: {exc.response.status_code}", raw={})
        except httpx.RequestError as exc:
            logger.error("Stripe ulanish xatosi: %s", exc)
            return ProviderResult(success=False, error=f"Stripe bilan bog'lanib bo'lmadi: {exc}", raw={})
        except Exception as exc:
            logger.exception("Stripe kutilmagan xato")
            return ProviderResult(success=False, error=str(exc), raw={})


# ─── Payment service ──────────────────────────────────────────────────────────

class PaymentService:
    """
    View'dan chaqiriladigan yagona kirish nuqtasi.

    Karta hashini yaratib Payment yozuvini saqlaydi, keyin
    tanlangan provayderga to'lovni uzatadi va natijani qaytaradi.
    """

    def __init__(self):
        from django.conf import settings

        self._providers: dict[str, BaseProvider] = {
            "payme": PaymeProvider(
                merchant_id=getattr(settings, "PAYME_MERCHANT_ID", ""),
                secret_key=getattr(settings, "PAYME_SECRET_KEY", ""),
                test_mode=getattr(settings, "PAYME_TEST_MODE", True),
            ),
            "stripe": StripeProvider(
                secret_key=getattr(settings, "STRIPE_SECRET_KEY", ""),
            ),
        }

    def pay(
        self,
        card_number: str,
        expire: str,
        amount: Decimal,
        currency: str,
        provider_name: str,
    ):
        from config.security import _search_token

        from .models import Payment

        payment = Payment.objects.create(
            card_number_hash=_search_token(card_number),
            amount=amount,
            currency=currency,
            provider=provider_name,
            status=Payment.Status.PENDING,
        )

        try:
            provider = self._providers[provider_name]
            result = provider.charge(card_number, expire, amount, currency)

            if result.success:
                payment.status = Payment.Status.SUCCESS
                payment.provider_transaction_id = result.transaction_id
            else:
                payment.status = Payment.Status.FAILED
                payment.error_message = result.error

            payment.provider_response = result.raw

        except KeyError:
            payment.status = Payment.Status.FAILED
            payment.error_message = f"Noto'g'ri provaydar: {provider_name}"
            logger.error("Noto'g'ri provaydar tanlandi: %s", provider_name)

        except Exception:
            payment.status = Payment.Status.FAILED
            payment.error_message = "Kutilmagan server xatosi"
            logger.exception("PaymentService.pay muvaffaqiyatsiz: payment_id=%d", payment.pk)

        payment.save(update_fields=[
            "status",
            "provider_transaction_id",
            "error_message",
            "provider_response",
            "updated_at",
        ])
        return payment
