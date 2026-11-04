from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.response import Response
from rest_framework.views import APIView

from .views import DowntimeRecordViewSet, MaintenancePlanViewSet, MaintenanceStatusView, MaintenanceTypeViewSet, RecurringProblemView, ServiceRecordViewSet, TechnicianViewSet, VehicleAvailabilityView, VehicleReadingViewSet, VehicleViewSet, WorkOrderExpenseViewSet, WorkOrderViewSet


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
router.register("work-orders", WorkOrderViewSet, basename="work-order")
router.register("work-order-expenses", WorkOrderExpenseViewSet, basename="work-order-expense")
router.register("downtime", DowntimeRecordViewSet, basename="downtime")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("maintenance-status/upcoming/", MaintenanceStatusView.as_view(), {"status_filter": "upcoming"}, name="maintenance-upcoming"),
    path("maintenance-status/overdue/", MaintenanceStatusView.as_view(), {"status_filter": "overdue"}, name="maintenance-overdue"),
    path("vehicles/<int:vehicle_id>/maintenance-status/", MaintenanceStatusView.as_view(), name="vehicle-maintenance-status"),
    path("vehicles/<int:vehicle_id>/availability/", VehicleAvailabilityView.as_view(), name="vehicle-availability"),
    path("recurring-problems/", RecurringProblemView.as_view(), name="recurring-problems"),
    path("vehicles/<int:vehicle_id>/recurring-problems/", RecurringProblemView.as_view(), name="vehicle-recurring-problems"),
    *router.urls,
]
