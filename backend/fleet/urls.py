from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.response import Response
from rest_framework.views import APIView

from .views import MaintenancePlanViewSet, MaintenanceStatusView, MaintenanceTypeViewSet, ServiceRecordViewSet, TechnicianViewSet, VehicleReadingViewSet, VehicleViewSet


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("technicians", TechnicianViewSet, basename="technician")
router.register("maintenance-types", MaintenanceTypeViewSet, basename="maintenance-type")
router.register("maintenance-plans", MaintenancePlanViewSet, basename="maintenance-plan")
router.register("service-records", ServiceRecordViewSet, basename="service-record")
router.register("readings", VehicleReadingViewSet, basename="reading")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("maintenance-status/upcoming/", MaintenanceStatusView.as_view(), {"status_filter": "upcoming"}, name="maintenance-upcoming"),
    path("maintenance-status/overdue/", MaintenanceStatusView.as_view(), {"status_filter": "overdue"}, name="maintenance-overdue"),
    path("vehicles/<int:vehicle_id>/maintenance-status/", MaintenanceStatusView.as_view(), name="vehicle-maintenance-status"),
    *router.urls,
]
