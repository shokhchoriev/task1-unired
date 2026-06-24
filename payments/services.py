"""
Payment service layer.

Hierarchy:
  PaymentService          ← entry point (called from views)
    └── PaymeProvider     ← Payme Merchant API (httpx)
    └── StripeProvider    ← Stripe API (official stripe SDK)
"""

import base64
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional, Union

import httpx
import stripe

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
        ext_id: Optional[str] = None,
    ) -> ProviderResult:
        """Charge a card and return a ProviderResult."""


# ─── Payme provider ──────────────────────────────────────────────────────────

class PaymeProvider(BaseProvider):
    """
    Payme Merchant API bilan ishlaydi.

    To'lov ketma-ketligi:
      1. cards.create  → karta token olish
      2. cards.get_verify_code → OTP yuborish
      3. receipts.create → chek yaratish
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
        year = parts[1][-2:]
        return f"{year}{month}"

    def charge(
        self,
        card_number: str,
        expire: str,
        amount: Decimal,
        currency: str,
        ext_id: Optional[str] = None,
    ) -> ProviderResult:
        payme_expire = self._parse_expire(expire)
        amount_tiyin = int(amount * 100)

        try:
            with httpx.Client(timeout=30) as client:
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

                verify_resp = self._rpc(client, "cards.get_verify_code", {"token": card_token})
                if "error" in verify_resp:
                    err = verify_resp["error"]
                    return ProviderResult(
                        success=False,
                        error=err.get("message", "OTP yuborishda xatolik"),
                        raw=verify_resp,
                    )

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
                return ProviderResult(success=True, transaction_id=invoice_id, raw=receipt_resp)

        except httpx.HTTPStatusError as exc:
            logger.error("Payme HTTP xatosi: %s", exc)
            return ProviderResult(success=False, error=f"Payme HTTP {exc.response.status_code}", raw={})
        except httpx.RequestError as exc:
            logger.error("Payme ulanish xatosi: %s", exc)
            return ProviderResult(success=False, error=f"Payme bilan bog'lanib bo'lmadi: {exc}", raw={})
        except Exception:
            logger.exception("Payme kutilmagan xato")
            return ProviderResult(success=False, error="Unexpected Payme error", raw={})


# ─── Stripe provider ─────────────────────────────────────────────────────────

class StripeProvider(BaseProvider):
    """
    Stripe API via the official stripe SDK.

    Two payment paths:

    charge()  — used by the REST API (/pay/).  Creates a PaymentMethod from raw
                card data and immediately confirms a PaymentIntent.  Raw card
                numbers are acceptable here because this endpoint is server-to-
                server (API clients, Postman, automated tests).

    create_checkout_session()  — used by the Telegram bot.  Redirects the user
                to a Stripe-hosted checkout page; no card data ever touches this
                server.  The resulting PaymentIntent is tracked via webhook.

    ext_id is stored in PaymentIntent metadata so it is visible in the Stripe
    dashboard and echoed back in webhook events.
    """

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def _parse_expire(self, expire: str) -> tuple:
        """MM/YY or MM/YYYY → (month_str, 4-digit-year_str)."""
        parts = expire.split("/")
        month = parts[0]
        year = parts[1] if len(parts[1]) == 4 else f"20{parts[1]}"
        return month, year

    @staticmethod
    def _to_dict(stripe_obj) -> dict:
        """Convert a Stripe SDK object to a plain Python dict for JSON storage."""
        try:
            return json.loads(str(stripe_obj))
        except Exception:
            return {}

    def charge(
        self,
        card_number: str,
        expire: str,
        amount: Decimal,
        currency: str,
        ext_id: Optional[str] = None,
    ) -> ProviderResult:
        stripe.api_key = self.secret_key
        exp_month, exp_year = self._parse_expire(expire)
        # Stripe amounts: smallest currency unit (cents for USD; whole units for UZS).
        amount_units = int(amount * 100) if currency.upper() == "USD" else int(amount)

        try:
            pm = stripe.PaymentMethod.create(
                type="card",
                card={
                    "number": card_number,
                    "exp_month": int(exp_month),
                    "exp_year": int(exp_year),
                },
            )

            intent = stripe.PaymentIntent.create(
                amount=amount_units,
                currency=currency.lower(),
                payment_method=pm.id,
                confirm=True,
                payment_method_types=["card"],
                metadata={"ext_id": str(ext_id)} if ext_id else {},
            )

            succeeded = intent.status == "succeeded"
            return ProviderResult(
                success=succeeded,
                transaction_id=intent.id,
                error="" if succeeded else f"Payment status: {intent.status}",
                raw=self._to_dict(intent),
            )

        except stripe.error.CardError as exc:
            return ProviderResult(
                success=False,
                error=exc.user_message or str(exc),
                raw=exc.json_body or {},
            )
        except stripe.error.InvalidRequestError as exc:
            logger.error("Stripe invalid request: %s", exc)
            return ProviderResult(success=False, error=str(exc), raw=exc.json_body or {})
        except stripe.error.AuthenticationError:
            logger.error("Stripe authentication failed — check STRIPE_SECRET_KEY")
            return ProviderResult(success=False, error="Stripe authentication failed", raw={})
        except stripe.error.StripeError as exc:
            logger.error("Stripe error: %s", exc)
            return ProviderResult(success=False, error=str(exc), raw=exc.json_body or {})
        except Exception:
            logger.exception("StripeProvider.charge unexpected error")
            return ProviderResult(success=False, error="Unexpected error", raw={})

    def create_checkout_session(
        self,
        amount: Decimal,
        currency: str,
        ext_id: str,
        success_url: str,
        cancel_url: str,
    ) -> ProviderResult:
        """
        Create a Stripe Checkout Session and return its URL.

        The underlying PaymentIntent ID is returned as transaction_id so the
        caller can store it for webhook reconciliation.
        """
        stripe.api_key = self.secret_key
        amount_units = int(amount * 100) if currency.upper() == "USD" else int(amount)

        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": amount_units,
                        "product_data": {"name": "To'lov"},
                    },
                    "quantity": 1,
                }],
                success_url=success_url,
                cancel_url=cancel_url,
                payment_intent_data={
                    "metadata": {"ext_id": ext_id},
                },
            )
            return ProviderResult(
                success=True,
                transaction_id=session.payment_intent or "",
                raw={"url": session.url, "session_id": session.id},
            )
        except stripe.error.StripeError as exc:
            logger.error("Stripe checkout session error: %s", exc)
            return ProviderResult(success=False, error=str(exc), raw={})
        except Exception:
            logger.exception("StripeProvider.create_checkout_session unexpected error")
            return ProviderResult(success=False, error="Unexpected error", raw={})

    def refund(self, payment_intent_id: str) -> ProviderResult:
        """Create a full refund for a PaymentIntent."""
        stripe.api_key = self.secret_key
        try:
            refund = stripe.Refund.create(payment_intent=payment_intent_id)
            return ProviderResult(
                success=True,
                transaction_id=refund.id,
                raw=self._to_dict(refund),
            )
        except stripe.error.InvalidRequestError as exc:
            logger.error("Stripe refund invalid request: %s", exc)
            return ProviderResult(success=False, error=str(exc), raw=exc.json_body or {})
        except stripe.error.StripeError as exc:
            logger.error("Stripe refund error: %s", exc)
            return ProviderResult(success=False, error=str(exc), raw=exc.json_body or {})
        except Exception:
            logger.exception("StripeProvider.refund unexpected error")
            return ProviderResult(success=False, error="Unexpected error", raw={})


# ─── Payment service ──────────────────────────────────────────────────────────

class PaymentService:
    """
    Single entry point called from views.

    Creates and persists a Payment record, dispatches to the chosen provider,
    and updates the record with the outcome.
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
        ext_id: Optional[str] = None,
    ):
        from config.security import _search_token
        from .models import Payment

        resolved_ext_id = ext_id if ext_id else str(uuid.uuid4())

        payment = Payment.objects.create(
            ext_id=resolved_ext_id,
            card_number_hash=_search_token(card_number),
            amount=amount,
            currency=currency,
            provider=provider_name,
            status=Payment.Status.PENDING,
        )

        try:
            provider = self._providers[provider_name]
            result = provider.charge(card_number, expire, amount, currency, ext_id=resolved_ext_id)

            if result.success:
                payment.status = Payment.Status.SUCCESS
                payment.provider_transaction_id = result.transaction_id
            else:
                payment.status = Payment.Status.FAILED
                payment.error_message = result.error

            payment.provider_response = result.raw

        except KeyError:
            payment.status = Payment.Status.FAILED
            payment.error_message = f"Unknown provider: {provider_name}"
            logger.error("Unknown provider: %s", provider_name)

        except Exception:
            payment.status = Payment.Status.FAILED
            payment.error_message = "Unexpected server error"
            logger.exception("PaymentService.pay failed: payment_id=%d", payment.pk)

        payment.save(update_fields=[
            "status",
            "provider_transaction_id",
            "error_message",
            "provider_response",
            "updated_at",
        ])
        return payment

    def checkout(
        self,
        amount: Decimal,
        currency: str,
        ext_id: Optional[str] = None,
    ):
        """
        Create a Stripe Checkout Session for the given amount/currency.

        Returns (checkout_url, Payment).  The Payment record is created with
        PENDING status and updated with provider_transaction_id after the session
        is created.  The existing webhook handler (payment_intent.succeeded)
        reconciles the outcome — no additional webhook event type needed.
        """
        from django.conf import settings
        from .models import Payment

        resolved_ext_id = ext_id or str(uuid.uuid4())
        success_url = getattr(settings, "STRIPE_SUCCESS_URL", "https://t.me/")
        cancel_url = getattr(settings, "STRIPE_CANCEL_URL", "https://t.me/")

        payment = Payment.objects.create(
            ext_id=resolved_ext_id,
            card_number_hash="",  # no card number for hosted checkout
            amount=amount,
            currency=currency,
            provider=Payment.Provider.STRIPE,
            status=Payment.Status.PENDING,
        )

        provider = self._providers.get("stripe")
        if not isinstance(provider, StripeProvider):
            payment.status = Payment.Status.FAILED
            payment.error_message = "Stripe provider not configured"
            payment.save(update_fields=["status", "error_message", "updated_at"])
            return "", payment

        result = provider.create_checkout_session(
            amount=amount,
            currency=currency,
            ext_id=resolved_ext_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )

        checkout_url = result.raw.get("url", "")
        if result.success:
            payment.provider_transaction_id = result.transaction_id
        else:
            payment.status = Payment.Status.FAILED
            payment.error_message = result.error
            checkout_url = ""

        payment.save(update_fields=["provider_transaction_id", "status", "error_message", "updated_at"])
        return checkout_url, payment

    def refund(self, payment):
        """Issue a full refund for a successful Stripe payment, update DB atomically."""
        from django.db import transaction
        from .models import Payment as PaymentModel

        provider = self._providers.get(payment.provider)
        if not isinstance(provider, StripeProvider):
            raise ValueError(f"Refunds not supported for provider '{payment.provider}'")

        result = provider.refund(payment.provider_transaction_id)

        if result.success:
            with transaction.atomic():
                locked = PaymentModel.objects.select_for_update().get(pk=payment.pk)
                locked.refund_id = result.transaction_id
                locked.status = PaymentModel.Status.REFUNDED
                locked.save(update_fields=["refund_id", "status", "updated_at"])

        return result
