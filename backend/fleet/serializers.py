from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import MaintenancePlan, MaintenanceType, ServiceRecord, Technician, Vehicle, VehicleReading, WorkOrder


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


class MaintenanceStatusSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(source="plan.id")
    vehicle_id = serializers.IntegerField(source="vehicle.id")
    vehicle_identifier = serializers.CharField(source="vehicle.vehicle_identifier")
    maintenance_type_id = serializers.IntegerField(source="maintenance_type.id")
    maintenance_type = serializers.CharField(source="maintenance_type.name")
    status = serializers.CharField()
    due_criteria = serializers.ListField(child=serializers.CharField())
    criteria = serializers.ListField()
    latest_service_id = serializers.SerializerMethodField()
    next_due_mileage = serializers.IntegerField(allow_null=True)
    next_due_engine_hours = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    next_due_date = serializers.DateField(allow_null=True)
    evaluated_at = serializers.DateTimeField()

    def get_latest_service_id(self, obj):
        return obj["latest_service"].id if obj["latest_service"] else None


class WorkOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrder
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        vehicle = attrs.get("vehicle", getattr(self.instance, "vehicle", None))
        plan = attrs.get("maintenance_plan", getattr(self.instance, "maintenance_plan", None))
        if plan and vehicle and plan.vehicle_id != vehicle.id:
            raise serializers.ValidationError({"maintenance_plan": "The maintenance plan must belong to the selected vehicle."})
        description = attrs.get("problem_description", getattr(self.instance, "problem_description", ""))
        if not description or not description.strip():
            raise serializers.ValidationError({"problem_description": "A problem description is required."})
        reported_date = attrs.get("reported_date", getattr(self.instance, "reported_date", None))
        target_date = attrs.get("target_completion_date", getattr(self.instance, "target_completion_date", None))
        if target_date and reported_date and target_date < reported_date:
            raise serializers.ValidationError({"target_completion_date": "Target completion cannot be before the reported date."})
        if self.instance and "status" in attrs and attrs["status"] != self.instance.status:
            if not self.instance.can_transition_to(attrs["status"]):
                raise serializers.ValidationError({"status": f"Cannot transition from {self.instance.status} to {attrs['status']}."})
        return attrs
