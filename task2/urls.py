from django.urls import path
from .views import json_rpc_view

urlpatterns = [
    path('', json_rpc_view, name='json_rpc'),
]