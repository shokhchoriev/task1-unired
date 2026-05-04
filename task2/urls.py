from django.urls import path
from .views import json_rpc_view, transfer_create, transfer_confirm, transfer_cancel, transfer_state, transfer_history
from .utils import log_transfer_method

urlpatterns = [
    path('', json_rpc_view, name='json_rpc'),
    path('transfer/create/', log_transfer_method(transfer_create), name='transfer_create'),
    path('transfer/confirm/<str:ext_id>/', log_transfer_method(transfer_confirm), name='transfer_confirm'),
    path('transfer/cancel/<str:ext_id>/', log_transfer_method(transfer_cancel), name='transfer_cancel'),
    path('transfer/state/<str:ext_id>/', log_transfer_method(transfer_state), name='transfer_state'),
    path('transfer/history/', log_transfer_method(transfer_history), name='transfer_history'),
]