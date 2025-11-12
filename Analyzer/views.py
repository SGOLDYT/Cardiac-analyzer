from django.shortcuts import render
from . import dash_apps

# Create your views here.
def home (request):
    return render(request, "inicio/index.html", {})
