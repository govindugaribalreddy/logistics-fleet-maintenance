import pytest
from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_endpoint():
    user = User.objects.create_user(username="health-manager", password="test-password")
    user.groups.add(Group.objects.create(name="Fleet Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
