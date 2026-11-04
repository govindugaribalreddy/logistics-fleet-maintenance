from decimal import Decimal

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import DowntimeRecord, MaintenancePlan, MaintenanceType, ServiceRecord, Technician, Vehicle, VehicleReading, WorkOrder, WorkOrderExpense
from .pagination import FleetPagination
from .maintenance_status import classify_plans, maintenance_plan_queryset
from .permissions import FleetRolePermission, MaintenanceStatusPermission, has_role, TECHNICIAN
from .recurring_problems import DEFAULT_WINDOW_DAYS, analyze_recurring_problems
from .serializers import DowntimeRecordSerializer, MaintenancePlanSerializer, MaintenanceStatusSerializer, MaintenanceTypeSerializer, RecurringProblemSerializer, ServiceRecordSerializer, TechnicianSerializer, VehicleReadingSerializer, VehicleSerializer, WorkOrderAssignmentSerializer, WorkOrderExpenseSerializer, WorkOrderSerializer


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested operation conflicts with existing data."
    default_code = "conflict"


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    pagination_class = FleetPagination
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("vehicle_identifier", "vin", "make", "model", "license_plate")
    ordering_fields = ("vehicle_identifier", "make", "model", "year", "mileage", "created_at")
    ordering = ("vehicle_identifier",)
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("operational_status")
        if status_value:
            queryset = queryset.filter(operational_status=status_value)
        make = self.request.query_params.get("make")
        if make:
            queryset = queryset.filter(make__iexact=make)
        model = self.request.query_params.get("model")
        if model:
            queryset = queryset.filter(model__iexact=model)
        return queryset

    def perform_destroy(self, instance):
        if instance.service_records.exists():
            raise ConflictError("Vehicles with historical service records cannot be deleted.")
        instance.delete()


class TechnicianViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Technician.objects.all()
    serializer_class = TechnicianSerializer
    pagination_class = FleetPagination
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("name", "email", "phone", "skills")
    ordering_fields = ("name", "email", "created_at")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        active = self.request.query_params.get("active")
        if active is not None:
            queryset = queryset.filter(active=active.lower() in ("1", "true", "yes"))
        return queryset


class MaintenanceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaintenanceType.objects.all()
    serializer_class = MaintenanceTypeSerializer
    pagination_class = FleetPagination
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")
    permission_classes = (FleetRolePermission,)


class MaintenancePlanViewSet(viewsets.ModelViewSet):
    queryset = MaintenancePlan.objects.select_related("vehicle", "maintenance_type").all()
    serializer_class = MaintenancePlanSerializer
    pagination_class = FleetPagination
    filter_backends = (OrderingFilter,)
    ordering_fields = ("vehicle", "maintenance_type", "enabled", "created_at", "updated_at")
    ordering = ("vehicle", "maintenance_type")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, TECHNICIAN):
            queryset = queryset.filter(vehicle__service_records__technician__email__iexact=self.request.user.email).distinct()
        vehicle = self.request.query_params.get("vehicle")
        if vehicle:
            queryset = queryset.filter(vehicle_id=vehicle)
        enabled = self.request.query_params.get("enabled")
        if enabled is not None:
            queryset = queryset.filter(enabled=enabled.lower() in ("1", "true", "yes"))
        return queryset


class ServiceRecordViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ServiceRecord.objects.select_related("vehicle", "service_type", "technician").all()
    serializer_class = ServiceRecordSerializer
    pagination_class = FleetPagination
    filter_backends = (OrderingFilter,)
    ordering_fields = ("service_date", "mileage", "total_cost", "created_at")
    ordering = ("-service_date", "-created_at")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, TECHNICIAN):
            queryset = queryset.filter(technician__email__iexact=self.request.user.email)
        for field in ("vehicle", "service_type", "technician"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}_id": value})
        return queryset


class VehicleReadingViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = VehicleReading.objects.select_related("vehicle").all()
    serializer_class = VehicleReadingSerializer
    pagination_class = FleetPagination
    filter_backends = (OrderingFilter,)
    ordering_fields = ("recorded_at", "mileage", "engine_hours", "created_at")
    ordering = ("-recorded_at", "-id")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, TECHNICIAN):
            queryset = queryset.filter(vehicle__service_records__technician__email__iexact=self.request.user.email).distinct()
        for field in ("vehicle", "source"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field if field == "source" else f"{field}_id": value})
        recorded_after = self.request.query_params.get("recorded_after")
        if recorded_after:
            queryset = queryset.filter(recorded_at__gte=recorded_after)
        recorded_before = self.request.query_params.get("recorded_before")
        if recorded_before:
            queryset = queryset.filter(recorded_at__lte=recorded_before)
        return queryset


class WorkOrderViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin):
    queryset = WorkOrder.objects.select_related("vehicle", "maintenance_plan", "maintenance_plan__maintenance_type").all()
    serializer_class = WorkOrderSerializer
    pagination_class = FleetPagination
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("work_order_number", "problem_description", "vehicle__vehicle_identifier")
    ordering_fields = ("reported_date", "target_completion_date", "priority", "status", "estimated_cost", "created_at")
    ordering = ("-reported_date", "-created_at")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ("vehicle", "status", "priority", "category", "maintenance_plan"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}_id" if field in {"vehicle", "maintenance_plan"} else field: value})
        technician = self.request.query_params.get("technician")
        if technician:
            queryset = queryset.filter(assigned_technician_id=technician)
        assignment_status = self.request.query_params.get("assignment_status")
        if assignment_status == "assigned":
            queryset = queryset.filter(assigned_technician__isnull=False)
        elif assignment_status == "unassigned":
            queryset = queryset.filter(assigned_technician__isnull=True)
        return queryset

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        serializer = WorkOrderAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        work_order = self.get_object()
        work_order.assign_to(serializer.validated_data.get("technician"), request.user)
        work_order.refresh_from_db()
        return Response(self.get_serializer(work_order).data)


class WorkOrderExpenseViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin):
    queryset = WorkOrderExpense.objects.select_related("work_order").all()
    serializer_class = WorkOrderExpenseSerializer
    pagination_class = FleetPagination
    filter_backends = (OrderingFilter,)
    ordering_fields = ("expense_date", "expense_type", "quantity", "unit_cost", "created_at")
    ordering = ("-expense_date", "-created_at")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        work_order = self.request.query_params.get("work_order")
        if work_order:
            queryset = queryset.filter(work_order_id=work_order)
        expense_type = self.request.query_params.get("expense_type")
        if expense_type:
            queryset = queryset.filter(expense_type=expense_type)
        return queryset


class DowntimeRecordViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin):
    queryset = DowntimeRecord.objects.select_related("vehicle", "work_order").all()
    serializer_class = DowntimeRecordSerializer
    pagination_class = FleetPagination
    filter_backends = (OrderingFilter,)
    ordering_fields = ("start_time", "end_time", "vehicle", "created_at")
    ordering = ("-start_time", "-id")
    permission_classes = (FleetRolePermission,)

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ("vehicle", "work_order"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}_id": value})
        ongoing = self.request.query_params.get("ongoing")
        if ongoing is not None:
            queryset = queryset.filter(end_time__isnull=ongoing.lower() in ("1", "true", "yes"))
        return queryset


class VehicleAvailabilityView(APIView):
    permission_classes = (MaintenanceStatusPermission,)

    def get(self, request, vehicle_id):
        vehicle = Vehicle.objects.get(pk=vehicle_id)
        current = vehicle.downtime_records.filter(end_time__isnull=True).order_by("-start_time").first()
        return Response({
            "vehicle_id": vehicle.id,
            "vehicle_identifier": vehicle.vehicle_identifier,
            "available": current is None,
            "current_downtime_id": current.id if current else None,
        })


class RecurringProblemView(APIView):
    permission_classes = (MaintenanceStatusPermission,)

    def get(self, request, vehicle_id=None):
        raw_days = request.query_params.get("days", str(DEFAULT_WINDOW_DAYS))
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"days": "Must be a positive integer."})
        if days <= 0:
            raise serializers.ValidationError({"days": "Must be a positive integer."})
        if vehicle_id is not None:
            get_object_or_404(Vehicle, pk=vehicle_id)
        results = analyze_recurring_problems(vehicle_id=vehicle_id, days=days)
        return Response(RecurringProblemSerializer(results, many=True).data)


def _status_thresholds(request):
    values = {}
    for parameter, key, parser in (
        ("upcoming_days", "upcoming_days", int),
        ("upcoming_mileage", "upcoming_mileage", int),
        ("upcoming_engine_hours", "upcoming_engine_hours", Decimal),
    ):
        raw = request.query_params.get(parameter)
        if raw is not None:
            try:
                value = parser(raw)
            except (TypeError, ValueError):
                raise serializers.ValidationError({parameter: "Must be a nonnegative number."})
            if value < 0:
                raise serializers.ValidationError({parameter: "Must be a nonnegative number."})
            values[key] = value
    return values


class MaintenanceStatusView(APIView):
    permission_classes = (MaintenanceStatusPermission,)

    def get(self, request, vehicle_id=None, status_filter=None):
        thresholds = _status_thresholds(request)
        plans = maintenance_plan_queryset()
        if has_role(request.user, TECHNICIAN):
            plans = plans.filter(vehicle__service_records__technician__email__iexact=request.user.email).distinct()
        if vehicle_id is not None:
            plans = plans.filter(vehicle_id=vehicle_id)
        results = classify_plans(plans, **thresholds)
        requested_status = status_filter or request.query_params.get("status")
        if requested_status == "upcoming":
            results = [result for result in results if result["status"] in {"due_now", "due_soon"}]
        elif requested_status == "overdue":
            results = [result for result in results if result["status"] == "overdue"]
        elif requested_status:
            results = [result for result in results if result["status"] == requested_status]
        return Response(MaintenanceStatusSerializer(results, many=True).data)

