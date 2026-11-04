from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import DowntimeRecord, Vehicle, WorkOrder, WorkOrderExpense

pytestmark = pytest.mark.django_db


@pytest.fixture
def recurring_context():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="REPEAT-001", vin="1M8GDM9AXKP042799", make="Volvo", model="VNL",
        year=2024, license_plate="REPEAT-001", mileage=1000, engine_hours=Decimal("20"),
    )
    other = Vehicle.objects.create(
        vehicle_identifier="REPEAT-002", vin="1M8GDM9AXKP042700", make="Kenworth", model="T680",
        year=2024, license_plate="REPEAT-002",
    )
    return vehicle, other


@pytest.fixture
def manager_client():
    user = User.objects.create_user(username="recurring-manager", password="test-password")
    user.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_order(vehicle, number, category, reported_date):
    return WorkOrder.objects.create(
        work_order_number=number, vehicle=vehicle, category=category, priority="medium",
        problem_description=f"Repair {category} issue.", reported_date=reported_date,
    )


def test_repeated_category_groups_expenses_and_downtime(recurring_context, manager_client):
    vehicle, _ = recurring_context
    first = make_order(vehicle, "REPEAT-WO-1", "corrective", "2026-01-10")
    second = make_order(vehicle, "REPEAT-WO-2", "corrective", "2026-02-10")
    make_order(vehicle, "REPEAT-WO-3", "inspection", "2026-02-15")
    WorkOrderExpense.objects.create(work_order=first, expense_type="parts", description="Belt", quantity="2.345", unit_cost="12.34", expense_date="2026-01-10")
    WorkOrderExpense.objects.create(work_order=second, expense_type="labor", description="Labor", quantity="1", unit_cost="10.00", expense_date="2026-02-10")
    start = timezone.make_aware(datetime(2026, 1, 10, 8, 0))
    DowntimeRecord.objects.create(vehicle=vehicle, work_order=first, start_time=start, end_time=start + timedelta(hours=2), reason="Repair")

    response = manager_client.get("/api/recurring-problems/?days=365")
    assert response.status_code == 200
    corrective = next(item for item in response.data if item["issue_category"] == "corrective")
    assert corrective["repeat_repair_count"] == 2
    assert corrective["work_order_ids"] == [first.id, second.id]
    assert corrective["total_repair_expenses"] == "38.94"
    assert corrective["downtime_seconds"] == 7200
    assert manager_client.get(f"/api/vehicles/{vehicle.id}/recurring-problems/?days=365").data[0]["vehicle_id"] == vehicle.id


def test_categories_and_date_boundaries_are_distinct(recurring_context, manager_client):
    vehicle, _ = recurring_context
    boundary = make_order(vehicle, "BOUNDARY-WO", "corrective", "2025-12-31")
    included = make_order(vehicle, "INCLUDED-WO", "corrective", "2026-01-01")
    make_order(vehicle, "DIFFERENT-WO", "emergency", "2026-01-02")
    response = manager_client.get("/api/recurring-problems/?days=307")
    assert response.status_code == 200
    assert all(boundary.id not in item["work_order_ids"] for item in response.data)
    corrective = next(item for item in response.data if item["issue_category"] == "corrective")
    assert corrective["repeat_repair_count"] == 1
    assert corrective["work_order_ids"] == [included.id]
    assert {item["issue_category"] for item in response.data} == {"corrective", "emergency"}


def test_vehicle_without_repair_history_returns_empty_and_requires_auth(recurring_context, manager_client):
    _, other = recurring_context
    assert APIClient().get("/api/recurring-problems/").status_code == 401
    response = manager_client.get(f"/api/vehicles/{other.id}/recurring-problems/?days=30")
    assert response.status_code == 200
    assert response.data == []

