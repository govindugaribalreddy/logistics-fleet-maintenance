from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import DowntimeRecord, Vehicle, WorkOrder

pytestmark = pytest.mark.django_db


@pytest.fixture
def downtime_context():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="DOWN-001", vin="1M8GDM9AXKP042799", make="Freightliner", model="Cascadia",
        year=2024, license_plate="DOWN-001", mileage=1000, engine_hours=Decimal("20"),
    )
    work_order = WorkOrder.objects.create(
        work_order_number="DOWN-WO-001", vehicle=vehicle, category="corrective", priority="high",
        problem_description="Repair a failed alternator.",
    )
    return vehicle, work_order


@pytest.fixture
def manager_client():
    user = User.objects.create_user(username="downtime-manager", password="test-password")
    user.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_ongoing_downtime_is_available_via_history_and_is_idempotent(downtime_context, manager_client):
    vehicle, work_order = downtime_context
    start = timezone.now() - timedelta(hours=2)
    payload = {"vehicle": vehicle.id, "work_order": work_order.id, "start_time": start.isoformat(), "reason": "Alternator failure"}
    first = manager_client.post("/api/downtime/", payload, format="json")
    second = manager_client.post("/api/downtime/", {**payload, "reason": "Repeated request"}, format="json")
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.data["id"] == first.data["id"]
    assert DowntimeRecord.objects.filter(vehicle=vehicle, end_time__isnull=True).count() == 1
    assert WorkOrder.objects.get(pk=work_order.pk).status == WorkOrder.Status.IN_PROGRESS
    availability = manager_client.get(f"/api/vehicles/{vehicle.id}/availability/")
    assert availability.status_code == 200
    assert availability.data["available"] is False


def test_completion_calculates_duration_and_completes_linked_work_order(downtime_context, manager_client):
    vehicle, work_order = downtime_context
    start = timezone.now() - timedelta(hours=3, minutes=15)
    created = manager_client.post("/api/downtime/", {"vehicle": vehicle.id, "work_order": work_order.id, "start_time": start.isoformat(), "reason": "Repair"}, format="json")
    end = start + timedelta(hours=2, minutes=30)
    completed = manager_client.patch(f"/api/downtime/{created.data['id']}/", {"end_time": end.isoformat()}, format="json")
    assert completed.status_code == 200
    assert completed.data["duration_seconds"] == 9000
    assert completed.data["vehicle_available"] is True
    assert WorkOrder.objects.get(pk=work_order.pk).status == WorkOrder.Status.COMPLETED
    assert manager_client.get(f"/api/vehicles/{vehicle.id}/availability/").data["available"] is True


def test_invalid_times_and_relationships_are_rejected(downtime_context, manager_client):
    vehicle, work_order = downtime_context
    other = Vehicle.objects.create(vehicle_identifier="DOWN-002", vin="1M8GDM9AXKP042700", make="Volvo", model="VNL", year=2024, license_plate="DOWN-002")
    start = timezone.now()
    bad_time = manager_client.post("/api/downtime/", {"vehicle": vehicle.id, "start_time": start.isoformat(), "end_time": (start - timedelta(minutes=1)).isoformat(), "reason": "Bad"}, format="json")
    mismatch = manager_client.post("/api/downtime/", {"vehicle": other.id, "work_order": work_order.id, "reason": "Mismatch"}, format="json")
    assert bad_time.status_code == 400
    assert mismatch.status_code == 400


def test_permissions_and_read_only_history(downtime_context, manager_client):
    vehicle, _ = downtime_context
    viewer = User.objects.create_user(username="downtime-viewer", password="test-password")
    viewer.groups.add(Group.objects.create(name="Read-only Viewer"))
    viewer_client = APIClient()
    viewer_client.force_authenticate(user=viewer)
    payload = {"vehicle": vehicle.id, "reason": "Inspection"}
    assert APIClient().get("/api/downtime/").status_code == 401
    created = manager_client.post("/api/downtime/", payload, format="json")
    assert created.status_code == 201
    assert viewer_client.get("/api/downtime/").status_code == 200
    assert viewer_client.patch(f"/api/downtime/{created.data['id']}/", {"notes": "No"}, format="json").status_code == 403

