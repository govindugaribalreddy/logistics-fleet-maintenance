from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from fleet.models import MaintenanceType, ServiceRecord, Technician, Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def vehicle():
    return Vehicle.objects.create(
        vehicle_identifier="TRUCK-001", vin="1M8GDM9AXKP042788", make="Freightliner",
        model="Cascadia", year=2024, license_plate="LOG-001", mileage=1000, engine_hours=Decimal("50.00"),
    )


@pytest.fixture
def maintenance_type():
    return MaintenanceType.objects.create(name="Oil change", mileage_interval=10000, engine_hour_interval=Decimal("250.00"))


def test_vehicle_rejects_negative_usage():
    vehicle = Vehicle(vehicle_identifier="TRUCK-002", vin="1M8GDM9AXKP042789", make="Ford", model="F-650", year=2023, license_plate="LOG-002", mileage=-1, engine_hours=-1)
    with pytest.raises(ValidationError):
        vehicle.full_clean()


def test_vehicle_identifier_is_unique(vehicle):
    with pytest.raises(IntegrityError):
        Vehicle.objects.create(vehicle_identifier=vehicle.vehicle_identifier, vin="1M8GDM9AXKP042790", make="Ford", model="F-650", year=2023, license_plate="LOG-003")


def test_service_record_relationships_and_costs(vehicle, maintenance_type):
    technician = Technician.objects.create(name="Alex Smith", email="alex@example.com", skills="Diesel")
    record = ServiceRecord.objects.create(
        vehicle=vehicle, service_date=date(2026, 1, 15), service_type=maintenance_type,
        mileage=1250, engine_hours=Decimal("65.50"), technician=technician,
        parts_cost=Decimal("120.25"), labor_cost=Decimal("80.00"), total_cost=Decimal("200.25"),
    )
    assert record.vehicle == vehicle
    assert record.service_type == maintenance_type
    assert record.technician == technician
    assert record.total_cost == Decimal("200.25")


def test_service_record_rejects_negative_cost(vehicle, maintenance_type):
    record = ServiceRecord(vehicle=vehicle, service_date=date.today(), service_type=maintenance_type, mileage=0, engine_hours=0, total_cost=-1)
    with pytest.raises(ValidationError):
        record.full_clean()
