from django.urls import path

from .views import RouteView

urlpatterns = [
    path("routes/", RouteView.as_view(), name="route-calculate"),
]
