from rest_framework import serializers

from .models import MaintenanceType, ServiceRecord, Technician, Vehicle


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


class ServiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceRecord
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

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
