from django.urls import path

from .views import stripe_refund, stripe_webhook

urlpatterns = [
    path("webhook/", stripe_webhook, name="stripe_webhook"),
    path("refund/", stripe_refund, name="stripe_refund"),
]
