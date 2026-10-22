from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.response import Response
from rest_framework.views import APIView

from .views import MaintenanceTypeViewSet, ServiceRecordViewSet, TechnicianViewSet, VehicleViewSet


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("technicians", TechnicianViewSet, basename="technician")
router.register("maintenance-types", MaintenanceTypeViewSet, basename="maintenance-type")
router.register("service-records", ServiceRecordViewSet, basename="service-record")

urlpatterns = [path("health/", HealthView.as_view(), name="health"), *router.urls]
