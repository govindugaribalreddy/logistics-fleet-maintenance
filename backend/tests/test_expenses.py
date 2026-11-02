from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from fleet.models import Vehicle, WorkOrder, WorkOrderExpense

pytestmark = pytest.mark.django_db


@pytest.fixture
def work_order():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="EXP-001", vin="1M8GDM9AXKP042799", make="International", model="LT",
        year=2024, license_plate="EXP-001", mileage=100, engine_hours=Decimal("10"),
    )
    return WorkOrder.objects.create(
        work_order_number="EXP-WO-001", vehicle=vehicle, category="corrective", priority="high",
        problem_description="Replace damaged alternator.",
    )


@pytest.fixture
def manager_client():
    user = User.objects.create_user(username="expense-manager", password="test-password")
    user.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_expense_creation_editing_rounding_and_work_order_total(work_order, manager_client):
    client = manager_client
    response = client.post("/api/work-order-expenses/", {"work_order": work_order.id, "expense_type": "parts", "description": "Fasteners", "quantity": "3.333", "unit_cost": "10.00", "expense_date": "2026-03-01", "supplier": "Parts Co", "reference": "INV-1"}, format="json")
    assert response.status_code == 201
    expense_id = response.data["id"]
    assert response.data["total"] == "33.33"
    assert client.get(f"/api/work-orders/{work_order.id}/").data["expense_total"] == "33.33"

    edited = client.patch(f"/api/work-order-expenses/{expense_id}/", {"quantity": "1.005", "unit_cost": "10.00"}, format="json")
    assert edited.status_code == 200
    assert edited.data["total"] == "10.05"
    assert client.get(f"/api/work-orders/{work_order.id}/").data["expense_total"] == "10.05"


def test_expense_rejects_invalid_values_and_completed_order_changes(work_order, manager_client):
    client = manager_client
    invalid = WorkOrderExpense(work_order=work_order, expense_type="labor", description="Labor", quantity=0, unit_cost=Decimal("10.00"))
    with pytest.raises(ValidationError):
        invalid.full_clean()

    created = client.post("/api/work-order-expenses/", {"work_order": work_order.id, "expense_type": "labor", "description": "Labor", "quantity": "1", "unit_cost": "10.00"}, format="json")
    assert created.status_code == 201
    work_order.status = WorkOrder.Status.ASSIGNED
    work_order.save()
    work_order.status = WorkOrder.Status.IN_PROGRESS
    work_order.save()
    work_order.status = WorkOrder.Status.COMPLETED
    work_order.save()
    blocked_create = client.post("/api/work-order-expenses/", {"work_order": work_order.id, "expense_type": "other", "description": "Fee", "quantity": "1", "unit_cost": "5.00"}, format="json")
    assert blocked_create.status_code == 400
    blocked_edit = client.patch(f"/api/work-order-expenses/{created.data['id']}/", {"unit_cost": "11.00"}, format="json")
    assert blocked_edit.status_code == 400


def test_expense_permissions_and_invalid_relationship(manager_client, work_order):
    viewer = User.objects.create_user(username="expense-viewer", password="test-password")
    viewer.groups.add(Group.objects.create(name="Read-only Viewer"))
    viewer_client = APIClient()
    viewer_client.force_authenticate(user=viewer)
    payload = {"work_order": work_order.id, "expense_type": "other", "description": "Fee", "quantity": "1", "unit_cost": "5.00"}
    assert viewer_client.get("/api/work-order-expenses/").status_code == 200
    assert viewer_client.post("/api/work-order-expenses/", payload, format="json").status_code == 403
    invalid = manager_client.post("/api/work-order-expenses/", {**payload, "work_order": 99999}, format="json")
    assert invalid.status_code == 400
