from django.urls import path

from .views import json_rpc_view
from .payment import payment_status

urlpatterns = [
    path("", json_rpc_view),
    path('payment/status/', payment_status, name='payment_status'),
    path("api/v1/rpc/", json_rpc_view, name="json_rpc"),
]
