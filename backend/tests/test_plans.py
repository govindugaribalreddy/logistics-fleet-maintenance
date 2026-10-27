from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from fleet.models import MaintenancePlan, MaintenanceType, ServiceRecord, Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan_context():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="PLAN-001", vin="1M8GDM9AXKP042799", make="Volvo", model="VNL",
        year=2024, license_plate="PLAN-001", mileage=10000, engine_hours=Decimal("500.00"),
    )
    maintenance_type = MaintenanceType.objects.create(name="Plan inspection")
    return vehicle, maintenance_type


def test_plan_requires_positive_scheduling_basis(plan_context):
    vehicle, maintenance_type = plan_context
    plan = MaintenancePlan(vehicle=vehicle, maintenance_type=maintenance_type)
    with pytest.raises(ValidationError):
        plan.full_clean()

    plan.mileage_interval = 0
    with pytest.raises(ValidationError):
        plan.full_clean()


def test_plan_relationship_is_unique(plan_context):
    vehicle, maintenance_type = plan_context
    MaintenancePlan.objects.create(vehicle=vehicle, maintenance_type=maintenance_type, mileage_interval=5000)
    with pytest.raises(ValidationError):
        MaintenancePlan(vehicle=vehicle, maintenance_type=maintenance_type, mileage_interval=6000).full_clean()


def test_plan_due_values_use_latest_applicable_service(plan_context):
    vehicle, maintenance_type = plan_context
    plan = MaintenancePlan.objects.create(vehicle=vehicle, maintenance_type=maintenance_type, mileage_interval=5000, engine_hour_interval=Decimal("100"), calendar_interval_days=30)
    assert plan.latest_completed_service is None
    assert plan.next_due_mileage == 15000
    assert plan.next_due_engine_hours == Decimal("600.00")
    assert plan.next_due_date == plan.created_at.date() + timedelta(days=30)

    first = ServiceRecord.objects.create(vehicle=vehicle, service_type=maintenance_type, service_date=date(2026, 1, 1), mileage=12000, engine_hours=Decimal("550"))
    second = ServiceRecord.objects.create(vehicle=vehicle, service_type=maintenance_type, service_date=date(2026, 2, 1), mileage=13000, engine_hours=Decimal("575"))
    plan.refresh_from_db()
    assert plan.latest_completed_service == second
    assert plan.next_due_mileage == 18000
    assert plan.next_due_engine_hours == Decimal("675.00")
    assert plan.next_due_date == date(2026, 3, 3)


def test_plan_api_is_authenticated_and_role_protected(plan_context):
    vehicle, maintenance_type = plan_context
    assert APIClient().get("/api/maintenance-plans/").status_code == 401

    viewer = User.objects.create_user(username="plan-viewer", email="plan-viewer@example.com", password="test-password")
    viewer.groups.add(Group.objects.create(name="Read-only Viewer"))
    viewer_client = APIClient()
    viewer_client.force_authenticate(user=viewer)
    assert viewer_client.post("/api/maintenance-plans/", {"vehicle": vehicle.id, "maintenance_type": maintenance_type.id, "mileage_interval": 5000}, format="json").status_code == 403

    manager = User.objects.create_user(username="plan-manager", email="plan-manager@example.com", password="test-password")
    manager.groups.add(Group.objects.create(name="Fleet Manager"))
    manager_client = APIClient()
    manager_client.force_authenticate(user=manager)
    created = manager_client.post("/api/maintenance-plans/", {"vehicle": vehicle.id, "maintenance_type": maintenance_type.id, "mileage_interval": 5000, "enabled": True}, format="json")
    assert created.status_code == 201
    assert created.data["next_due_mileage"] == 15000
    assert manager_client.patch(f"/api/maintenance-plans/{created.data['id']}/", {"enabled": False}, format="json").status_code == 200


def test_plan_api_rejects_empty_schedule(plan_context):
    vehicle, maintenance_type = plan_context
    manager = User.objects.create_user(username="plan-manager-empty", password="test-password")
    manager.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=manager)
    response = client.post("/api/maintenance-plans/", {"vehicle": vehicle.id, "maintenance_type": maintenance_type.id}, format="json")
    assert response.status_code == 400
