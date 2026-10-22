from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from fleet.models import MaintenanceType, ServiceRecord, Technician, Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def vehicle_data():
    return {
        "vehicle_identifier": "TRUCK-API-001",
        "vin": "1M8GDM9AXKP042799",
        "make": "Freightliner",
        "model": "Cascadia",
        "year": 2024,
        "license_plate": "API-001",
        "mileage": 1000,
        "engine_hours": "50.00",
        "operational_status": "active",
    }


@pytest.fixture
def related_objects():
    technician = Technician.objects.create(name="Alex Smith", email="api-tech@example.com")
    maintenance_type = MaintenanceType.objects.create(name="API oil change", mileage_interval=10000)
    return technician, maintenance_type


def test_vehicle_list_create_update_and_retrieve(api_client, vehicle_data):
    created = api_client.post("/api/vehicles/", vehicle_data, format="json")
    assert created.status_code == 201
    vehicle_id = created.data["id"]

    listed = api_client.get("/api/vehicles/")
    assert listed.status_code == 200
    assert listed.data["count"] == 1

    retrieved = api_client.get(f"/api/vehicles/{vehicle_id}/")
    assert retrieved.status_code == 200
    assert retrieved.data["vehicle_identifier"] == vehicle_data["vehicle_identifier"]

    updated = api_client.patch(f"/api/vehicles/{vehicle_id}/", {"mileage": 2500}, format="json")
    assert updated.status_code == 200
    assert updated.data["mileage"] == 2500


def test_vehicle_search_and_filters(api_client, vehicle_data):
    Vehicle.objects.create(**vehicle_data)
    other = {**vehicle_data, "vehicle_identifier": "TRUCK-API-002", "vin": "1M8GDM9AXKP042700", "license_plate": "API-002", "make": "Volvo", "operational_status": "inactive"}
    Vehicle.objects.create(**other)

    response = api_client.get("/api/vehicles/?search=Freightliner&operational_status=active")
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_vehicle_duplicate_and_invalid_input_return_consistent_errors(api_client, vehicle_data):
    assert api_client.post("/api/vehicles/", vehicle_data, format="json").status_code == 201
    duplicate = api_client.post("/api/vehicles/", {**vehicle_data, "vehicle_identifier": "TRUCK-API-002", "license_plate": "API-002"}, format="json")
    assert duplicate.status_code == 400
    assert "vin" in duplicate.data

    invalid = api_client.post("/api/vehicles/", {**vehicle_data, "mileage": -1}, format="json")
    assert invalid.status_code == 400
    assert "mileage" in invalid.data


def test_vehicle_missing_record_and_safe_delete(api_client, vehicle_data, related_objects):
    missing = api_client.get("/api/vehicles/99999/")
    assert missing.status_code == 404

    vehicle = Vehicle.objects.create(**vehicle_data)
    assert api_client.delete(f"/api/vehicles/{vehicle.id}/").status_code == 204

    vehicle = Vehicle.objects.create(
        vehicle_identifier="TRUCK-API-003", vin="1M8GDM9AXKP042701", make="Freightliner",
        model="Cascadia", year=2024, license_plate="API-003",
    )
    technician, maintenance_type = related_objects
    ServiceRecord.objects.create(vehicle=vehicle, service_type=maintenance_type, technician=technician, service_date="2026-01-01", mileage=10, engine_hours=Decimal("1"))
    blocked = api_client.delete(f"/api/vehicles/{vehicle.id}/")
    assert blocked.status_code == 409
    assert "historical service records" in blocked.data["detail"]


def test_pagination_and_read_only_reference_lists(api_client, vehicle_data, related_objects):
    for index in range(21):
        Vehicle.objects.create(**{**vehicle_data, "vehicle_identifier": f"TRUCK-PAGE-{index}", "vin": f"1M8GDM9AXKP04{2800 + index:03d}", "license_plate": f"PAGE-{index}"})
    response = api_client.get("/api/vehicles/?page_size=10")
    assert response.status_code == 200
    assert response.data["count"] == 21
    assert len(response.data["results"]) == 10

    assert api_client.get("/api/technicians/").status_code == 200
    assert api_client.get("/api/maintenance-types/").status_code == 200
    assert api_client.post("/api/technicians/", {"name": "Not allowed", "email": "no@example.com"}, format="json").status_code == 405


def test_service_record_create_list_and_related_validation(api_client, vehicle_data, related_objects):
    vehicle = Vehicle.objects.create(**vehicle_data)
    technician, maintenance_type = related_objects
    payload = {
        "vehicle": vehicle.id,
        "service_date": "2026-02-01",
        "service_type": maintenance_type.id,
        "description": "Oil and filter replacement",
        "mileage": 1200,
        "engine_hours": "60.50",
        "technician": technician.id,
        "parts_cost": "120.25",
        "labor_cost": "80.00",
        "total_cost": "200.25",
    }
    created = api_client.post("/api/service-records/", payload, format="json")
    assert created.status_code == 201
    assert created.data["total_cost"] == "200.25"

    listed = api_client.get(f"/api/service-records/?vehicle={vehicle.id}")
    assert listed.status_code == 200
    assert listed.data["count"] == 1

    invalid = api_client.post("/api/service-records/", {**payload, "vehicle": 99999}, format="json")
    assert invalid.status_code == 400
    assert "vehicle" in invalid.data

    negative = api_client.post("/api/service-records/", {**payload, "parts_cost": "-1"}, format="json")
    assert negative.status_code == 400
    assert "parts_cost" in negative.data
