from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from fleet.models import MaintenancePlan, MaintenanceType, Vehicle, WorkOrder

pytestmark = pytest.mark.django_db


@pytest.fixture
def work_order_context():
    vehicle = Vehicle.objects.create(
        vehicle_identifier="WO-001", vin="1M8GDM9AXKP042799", make="Peterbilt", model="579",
        year=2024, license_plate="WO-001", mileage=5000, engine_hours=Decimal("200"),
    )
    maintenance_type = MaintenanceType.objects.create(name="Work order service")
    plan = MaintenancePlan.objects.create(vehicle=vehicle, maintenance_type=maintenance_type, mileage_interval=10000)
    return vehicle, plan


def test_work_order_valid_transitions_and_terminal_states(work_order_context):
    vehicle, plan = work_order_context
    work_order = WorkOrder.objects.create(
        work_order_number="WO-0001", vehicle=vehicle, maintenance_plan=plan,
        category=WorkOrder.Category.CORRECTIVE, priority=WorkOrder.Priority.HIGH,
        problem_description="Brake warning light is active.", estimated_cost=Decimal("250.00"),
    )
    for state in (WorkOrder.Status.ASSIGNED, WorkOrder.Status.IN_PROGRESS, WorkOrder.Status.WAITING_FOR_PARTS, WorkOrder.Status.IN_PROGRESS, WorkOrder.Status.COMPLETED):
        work_order.transition_to(state)
        work_order.save()
    with pytest.raises(ValidationError):
        work_order.transition_to(WorkOrder.Status.OPEN)


def test_work_order_validates_description_dates_cost_and_plan_vehicle(work_order_context):
    vehicle, plan = work_order_context
    invalid = WorkOrder(
        work_order_number="WO-0002", vehicle=vehicle, maintenance_plan=plan,
        category="corrective", priority="high", problem_description=" ",
        reported_date="2026-03-10", target_completion_date="2026-03-01", estimated_cost=-1,
    )
    with pytest.raises(ValidationError):
        invalid.full_clean()

    other_vehicle = Vehicle.objects.create(vehicle_identifier="WO-002", vin="1M8GDM9AXKP042700", make="Volvo", model="VNL", year=2024, license_plate="WO-002")
    mismatch = WorkOrder(work_order_number="WO-0003", vehicle=other_vehicle, maintenance_plan=plan, category="corrective", priority="low", problem_description="Engine inspection required.")
    with pytest.raises(ValidationError):
        mismatch.full_clean()


def manager_client():
    user = User.objects.create_user(username="work-order-manager", password="test-password")
    user.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_work_order_api_authorization_crud_filtering_and_pagination(work_order_context):
    vehicle, plan = work_order_context
    assert APIClient().get("/api/work-orders/").status_code == 401

    viewer = User.objects.create_user(username="work-order-viewer", password="test-password")
    viewer.groups.add(Group.objects.create(name="Read-only Viewer"))
    viewer_client = APIClient()
    viewer_client.force_authenticate(user=viewer)
    assert viewer_client.post("/api/work-orders/", {}, format="json").status_code == 403

    client = manager_client()
    payload = {
        "work_order_number": "WO-API-001", "vehicle": vehicle.id, "maintenance_plan": plan.id,
        "category": "preventive", "priority": "high", "problem_description": "Replace worn brake pads.",
        "reported_date": "2026-03-01", "target_completion_date": "2026-03-05", "estimated_cost": "500.00",
    }
    created = client.post("/api/work-orders/", payload, format="json")
    assert created.status_code == 201
    work_order_id = created.data["id"]

    updated = client.patch(f"/api/work-orders/{work_order_id}/", {"status": "assigned"}, format="json")
    assert updated.status_code == 200
    assert updated.data["status"] == "assigned"

    invalid_transition = client.patch(f"/api/work-orders/{work_order_id}/", {"status": "completed"}, format="json")
    assert invalid_transition.status_code == 400

    for index in range(20):
        WorkOrder.objects.create(work_order_number=f"WO-PAGE-{index}", vehicle=vehicle, category="corrective", priority="low", problem_description="Routine inspection requested.")
    listing = client.get("/api/work-orders/?priority=low&page_size=10")
    assert listing.status_code == 200
    assert listing.data["count"] == 20
    assert len(listing.data["results"]) == 10
    assert client.get(f"/api/work-orders/{work_order_id}/").status_code == 200


def test_work_order_api_rejects_invalid_inputs(work_order_context):
    vehicle, plan = work_order_context
    client = manager_client()
    base = {"work_order_number": "WO-INVALID", "vehicle": vehicle.id, "category": "corrective", "priority": "low", "problem_description": "Inspect steering system."}
    negative = client.post("/api/work-orders/", {**base, "estimated_cost": "-1"}, format="json")
    assert negative.status_code == 400
    bad_plan = client.post("/api/work-orders/", {**base, "maintenance_plan": 99999}, format="json")
    assert bad_plan.status_code == 400
    bad_priority = client.post("/api/work-orders/", {**base, "priority": "urgent"}, format="json")
    assert bad_priority.status_code == 400
