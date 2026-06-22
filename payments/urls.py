from django.urls import path

from .views import pay

urlpatterns = [
    path("", pay, name="pay"),
]
