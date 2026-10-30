from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from fleet.models import Technician, Vehicle, WorkOrder, WorkOrderAssignmentHistory

pytestmark = pytest.mark.django_db


@pytest.fixture
def work_order():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="ASSIGN-001", vin="1M8GDM9AXKP042799", make="Kenworth", model="T680",
        year=2024, license_plate="ASSIGN-001", mileage=100, engine_hours=Decimal("10"),
    )
    return WorkOrder.objects.create(
        work_order_number="ASSIGN-WO-001", vehicle=vehicle, category="corrective", priority="medium",
        problem_description="Investigate a warning light.",
    )


@pytest.fixture
def technicians():
    return (
        Technician.objects.create(name="First Tech", email="first-assignment@example.com", active=True),
        Technician.objects.create(name="Second Tech", email="second-assignment@example.com", active=True),
        Technician.objects.create(name="Inactive Tech", email="inactive-assignment@example.com", active=False),
    )


@pytest.fixture
def manager_client():
    user = User.objects.create_user(username="assignment-manager", password="test-password")
    user.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def test_assignment_and_reassignment_preserve_history(work_order, technicians, manager_client):
    first, second, _ = technicians
    client, acting_user = manager_client

    assigned = client.post(f"/api/work-orders/{work_order.id}/assign/", {"technician": first.id}, format="json")
    assert assigned.status_code == 200
    assert assigned.data["assigned_technician"] == first.id
    reassigned = client.post(f"/api/work-orders/{work_order.id}/assign/", {"technician": second.id}, format="json")
    assert reassigned.status_code == 200

    history = list(WorkOrderAssignmentHistory.objects.filter(work_order=work_order).order_by("changed_at", "id"))
    assert len(history) == 2
    assert history[0].previous_technician_id is None
    assert history[0].new_technician_id == first.id
    assert history[0].acting_user_id == acting_user.id
    assert history[1].previous_technician_id == first.id
    assert history[1].new_technician_id == second.id
    assert history[1].acting_user_id == acting_user.id


def test_inactive_and_invalid_technicians_are_rejected(work_order, technicians, manager_client):
    _, _, inactive = technicians
    client, _ = manager_client
    inactive_response = client.post(f"/api/work-orders/{work_order.id}/assign/", {"technician": inactive.id}, format="json")
    assert inactive_response.status_code == 400
    invalid_response = client.post(f"/api/work-orders/{work_order.id}/assign/", {"technician": 99999}, format="json")
    assert invalid_response.status_code == 400
    assert not WorkOrderAssignmentHistory.objects.filter(work_order=work_order).exists()


def test_assignment_requires_manager_and_filters_work_orders(work_order, technicians, manager_client):
    first, _, _ = technicians
    viewer = User.objects.create_user(username="assignment-viewer", password="test-password")
    viewer.groups.add(Group.objects.create(name="Read-only Viewer"))
    viewer_client = APIClient()
    viewer_client.force_authenticate(user=viewer)
    assert viewer_client.post(f"/api/work-orders/{work_order.id}/assign/", {"technician": first.id}, format="json").status_code == 403

    client, _ = manager_client
    client.post(f"/api/work-orders/{work_order.id}/assign/", {"technician": first.id}, format="json")
    assert client.get(f"/api/work-orders/?technician={first.id}").data["count"] == 1
    assert client.get("/api/work-orders/?assignment_status=assigned").data["count"] == 1
    assert client.get("/api/work-orders/?assignment_status=unassigned").data["count"] == 0
