from django.urls import path
from .views import json_rpc_view


urlpatterns = [
    path('api/v1/rpc/', json_rpc_view, name='json_rpc_endpoint'),
] 