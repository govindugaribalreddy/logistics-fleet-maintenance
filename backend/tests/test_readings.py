from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from fleet.models import MaintenanceType, ServiceRecord, Technician, Vehicle, VehicleReading

pytestmark = pytest.mark.django_db


@pytest.fixture
def vehicle():
    return Vehicle.objects.create(
        vehicle_identifier="READING-001", vin="1M8GDM9AXKP042799", make="Ford", model="F-650",
        year=2024, license_plate="READ-001", mileage=1000, engine_hours=Decimal("50.00"),
    )


def test_reading_rejects_negative_values(vehicle):
    reading = VehicleReading(vehicle=vehicle, mileage=-1, engine_hours=Decimal("1"))
    with pytest.raises(ValidationError):
        reading.full_clean()


def test_readings_preserve_history_and_update_vehicle_atomically(vehicle):
    first = VehicleReading.record(vehicle_id=vehicle.id, mileage=1100, engine_hours=Decimal("55.00"), source="telematics")
    second = VehicleReading.record(vehicle_id=vehicle.id, mileage=1200, engine_hours=Decimal("60.00"), source="manual")
    vehicle.refresh_from_db()
    assert VehicleReading.objects.filter(vehicle=vehicle).count() == 2
    assert first.mileage == 1100
    assert second.mileage == 1200
    assert vehicle.mileage == 1200
    assert vehicle.engine_hours == Decimal("60.00")
    with pytest.raises(ValidationError):
        VehicleReading.record(vehicle_id=vehicle.id, mileage=1199, engine_hours=Decimal("60.00"))
    assert VehicleReading.objects.filter(vehicle=vehicle).count() == 2


def test_service_record_total_cost_is_calculated(vehicle):
    maintenance_type = MaintenanceType.objects.create(name="Reading service")
    record = ServiceRecord.objects.create(
        vehicle=vehicle, service_type=maintenance_type, service_date="2026-03-01",
        mileage=1200, engine_hours=Decimal("60"), parts_cost=Decimal("125.50"), labor_cost=Decimal("74.50"), total_cost=Decimal("999.99"),
    )
    assert record.total_cost == Decimal("200.00")


def test_reading_api_preserves_history_and_enforces_permissions(vehicle):
    technician = Technician.objects.create(name="Reading Tech", email="reading-tech@example.com")
    maintenance_type = MaintenanceType.objects.create(name="Reading assignment")
    ServiceRecord.objects.create(vehicle=vehicle, service_type=maintenance_type, technician=technician, service_date="2026-03-01", mileage=1000, engine_hours=Decimal("50"))
    user = User.objects.create_user(username="reading-tech", email=technician.email, password="test-password")
    user.groups.add(Group.objects.create(name="Technician"))
    client = APIClient()
    client.force_authenticate(user=user)

    created = client.post("/api/readings/", {"vehicle": vehicle.id, "mileage": 1100, "engine_hours": "55.00", "source": "manual"}, format="json")
    assert created.status_code == 201
    lower = client.post("/api/readings/", {"vehicle": vehicle.id, "mileage": 1099, "engine_hours": "55.00", "source": "manual"}, format="json")
    assert lower.status_code == 400
    assert client.get("/api/readings/?vehicle={}".format(vehicle.id)).data["count"] == 1
