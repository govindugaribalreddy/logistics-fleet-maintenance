from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from fleet.models import MaintenanceType, ServiceRecord, Technician, Vehicle

pytestmark = pytest.mark.django_db


def authenticated_client(username, email, role):
    user = User.objects.create_user(username=username, email=email, password="test-password")
    user.groups.add(Group.objects.create(name=role))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def vehicle():
    return Vehicle.objects.create(
        vehicle_identifier="AUTH-001", vin="1M8GDM9AXKP042799", make="Ford", model="F-650",
        year=2024, license_plate="AUTH-001", mileage=100, engine_hours=Decimal("10.00"),
    )


@pytest.fixture
def service_type():
    return MaintenanceType.objects.create(name="Auth inspection")


def test_unauthenticated_requests_are_rejected():
    assert APIClient().get("/api/vehicles/").status_code == 401
    assert APIClient().get("/api/health/").status_code == 401


def test_viewer_can_read_but_cannot_modify(vehicle):
    client = authenticated_client("viewer", "viewer@example.com", "Read-only Viewer")
    assert client.get("/api/vehicles/").status_code == 200
    assert client.patch(f"/api/vehicles/{vehicle.id}/", {"mileage": 200}, format="json").status_code == 403
    assert client.delete(f"/api/vehicles/{vehicle.id}/").status_code == 403


def test_technician_only_sees_and_creates_own_assigned_records(vehicle, service_type):
    tech = Technician.objects.create(name="Assigned Tech", email="tech@example.com")
    other_tech = Technician.objects.create(name="Other Tech", email="other@example.com")
    ServiceRecord.objects.create(vehicle=vehicle, service_type=service_type, technician=tech, service_date="2026-01-01", mileage=100, engine_hours=Decimal("10"))
    ServiceRecord.objects.create(vehicle=vehicle, service_type=service_type, technician=other_tech, service_date="2026-01-02", mileage=110, engine_hours=Decimal("11"))
    client = authenticated_client("tech", "tech@example.com", "Technician")

    response = client.get("/api/service-records/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["technician"] == tech.id

    payload = {"vehicle": vehicle.id, "service_type": service_type.id, "technician": other_tech.id, "service_date": "2026-02-01", "mileage": 120, "engine_hours": "12.00"}
    assert client.post("/api/service-records/", payload, format="json").status_code == 400
    payload["technician"] = tech.id
    assert client.post("/api/service-records/", payload, format="json").status_code == 201


def test_technician_cannot_modify_vehicles_and_manager_can(vehicle):
    tech_client = authenticated_client("tech-manager-test", "tech2@example.com", "Technician")
    assert tech_client.put(f"/api/vehicles/{vehicle.id}/", {"vehicle_identifier": "CHANGED"}, format="json").status_code == 403
    manager_client = authenticated_client("manager-auth-test", "manager-auth@example.com", "Fleet Manager")
    assert manager_client.patch(f"/api/vehicles/{vehicle.id}/", {"mileage": 999}, format="json").status_code == 200
