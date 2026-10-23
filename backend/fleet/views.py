from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import MaintenanceType, ServiceRecord, Technician, Vehicle
from .pagination import FleetPagination
from .permissions import FleetRolePermission, has_role, TECHNICIAN
from .serializers import MaintenanceTypeSerializer, ServiceRecordSerializer, TechnicianSerializer, VehicleSerializer


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

