from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.maintenance_status import classify_plan
from fleet.models import MaintenancePlan, MaintenanceType, ServiceRecord, Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def context():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="STATUS-001", vin="1M8GDM9AXKP042799", make="Mack", model="Anthem",
        year=2024, license_plate="STATUS-001", mileage=10000, engine_hours=Decimal("100"),
    )
    maintenance_type = MaintenanceType.objects.create(name="Status service")
    plan = MaintenancePlan.objects.create(vehicle=vehicle, maintenance_type=maintenance_type, mileage_interval=1000, engine_hour_interval=Decimal("10"), calendar_interval_days=30)
    return vehicle, maintenance_type, plan


def test_status_boundaries_and_combined_criteria(context):
    vehicle, maintenance_type, plan = context
    vehicle.mileage = 11000
    vehicle.engine_hours = Decimal("100")
    vehicle.save(update_fields=["mileage", "engine_hours", "updated_at"])
    plan.vehicle.refresh_from_db()
    result = classify_plan(plan, upcoming_mileage=100, upcoming_engine_hours=5, upcoming_days=3)
    assert result["status"] == "due_now"
    assert result["due_criteria"] == ["mileage"]

    vehicle.mileage = 10000
    vehicle.engine_hours = Decimal("110")
    vehicle.save(update_fields=["mileage", "engine_hours", "updated_at"])
    plan.vehicle.refresh_from_db()
    result = classify_plan(plan, upcoming_mileage=100, upcoming_engine_hours=5, upcoming_days=3)
    assert result["status"] == "due_now"
    assert "engine_hours" in result["due_criteria"]


def test_missing_service_reading_uses_current_vehicle_snapshot(context):
    vehicle, _, plan = context
    result = classify_plan(plan, upcoming_mileage=100)
    assert result["latest_service"] is None
    assert result["next_due_mileage"] == 11000
    assert result["status"] == "due_soon"


def test_overdue_and_timezone_aware_calendar_boundary(context):
    vehicle, maintenance_type, plan = context
    ServiceRecord.objects.create(
        vehicle=vehicle, service_type=maintenance_type, service_date=date.today() - timedelta(days=31),
        mileage=9000, engine_hours=Decimal("90"),
    )
    result = classify_plan(plan, now=timezone.now(), upcoming_days=0)
    assert result["status"] == "overdue"
    assert result["next_due_date"] == date.today() - timedelta(days=1)


@override_settings(MAINTENANCE_UPCOMING_MILEAGE=200)
def test_status_apis_filter_upcoming_and_overdue(context):
    vehicle, _, plan = context
    manager = User.objects.create_user(username="status-manager", password="test-password")
    manager.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=manager)

    upcoming = client.get("/api/maintenance-status/upcoming/")
    assert upcoming.status_code == 200
    assert upcoming.data[0]["status"] == "due_soon"

    vehicle.mileage = 12000
    vehicle.save(update_fields=["mileage", "updated_at"])
    overdue = client.get("/api/maintenance-status/overdue/")
    assert overdue.status_code == 200
    assert overdue.data[0]["plan_id"] == plan.id

    vehicle_status = client.get(f"/api/vehicles/{vehicle.id}/maintenance-status/")
    assert vehicle_status.status_code == 200
    assert vehicle_status.data[0]["vehicle_id"] == vehicle.id
