from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import MaintenancePlan, MaintenanceType, ServiceRecord, Technician, Vehicle, VehicleReading


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class TechnicianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Technician
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class MaintenanceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceType
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class MaintenancePlanSerializer(serializers.ModelSerializer):
    latest_completed_service = serializers.SerializerMethodField()
    next_due_mileage = serializers.IntegerField(read_only=True)
    next_due_engine_hours = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    next_due_date = serializers.DateField(read_only=True)
    is_due = serializers.BooleanField(read_only=True)

    class Meta:
        model = MaintenancePlan
        fields = (
            "id", "vehicle", "maintenance_type", "mileage_interval", "engine_hour_interval",
            "calendar_interval_days", "enabled", "created_at", "updated_at", "latest_completed_service",
            "next_due_mileage", "next_due_engine_hours", "next_due_date", "is_due",
        )
        read_only_fields = ("id", "created_at", "updated_at", "latest_completed_service", "next_due_mileage", "next_due_engine_hours", "next_due_date", "is_due")

    def validate(self, attrs):
        current = self.instance
        for field in ("mileage_interval", "engine_hour_interval", "calendar_interval_days"):
            value = attrs.get(field)
            if value is None and current is not None and field not in attrs:
                value = getattr(current, field)
            if value is not None and value <= 0:
                raise serializers.ValidationError({field: "Scheduling intervals must be positive."})
        if not any(
            attrs.get(field, getattr(current, field, None))
            for field in ("mileage_interval", "engine_hour_interval", "calendar_interval_days")
        ):
            raise serializers.ValidationError("At least one scheduling basis is required.")
        return attrs

    def get_latest_completed_service(self, obj):
        service = obj.latest_completed_service
        return service.id if service else None


class ServiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceRecord
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "total_cost")

    def validate(self, attrs):
        vehicle = attrs.get("vehicle")
        mileage = attrs.get("mileage")
        if vehicle and mileage is not None and mileage < 0:
            raise serializers.ValidationError({"mileage": "Mileage cannot be negative."})
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.groups.filter(name="Technician").exists():
            technician = attrs.get("technician")
            if technician is None or technician.email.lower() != request.user.email.lower():
                raise serializers.ValidationError({"technician": "Technicians may only create records assigned to themselves."})
        return attrs


class VehicleReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleReading
        fields = "__all__"
        read_only_fields = ("id", "created_at")

    def create(self, validated_data):
        request = self.context.get("request")
        vehicle = validated_data.get("vehicle")
        if request and request.user.is_authenticated and request.user.groups.filter(name="Technician").exists():
            if not vehicle.service_records.filter(technician__email__iexact=request.user.email).exists():
                raise serializers.ValidationError({"vehicle": "Technicians may only record readings for assigned vehicles."})
        try:
            validated_data["vehicle_id"] = validated_data.pop("vehicle").id
            return VehicleReading.record(**validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"reading": exc.messages}) from exc
