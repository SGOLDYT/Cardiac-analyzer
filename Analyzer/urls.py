from django.urls import path
from Analyzer import views

urlpatterns = [
    path("", views.home, name="index"),
]