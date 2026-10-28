from rest_framework.permissions import BasePermission


FLEET_MANAGER = "Fleet Manager"
TECHNICIAN = "Technician"
READ_ONLY_VIEWER = "Read-only Viewer"


def has_role(user, role):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name=role).exists())


class FleetRolePermission(BasePermission):
    message = "Your account does not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if has_role(request.user, FLEET_MANAGER):
            return True
        if view.basename in {"technician", "maintenance-type", "maintenance-plan"}:
            if view.basename == "maintenance-plan" and has_role(request.user, TECHNICIAN):
                return request.method in {"GET", "HEAD", "OPTIONS"}
            return request.method in {"GET", "HEAD", "OPTIONS"} and (
                has_role(request.user, TECHNICIAN) or has_role(request.user, READ_ONLY_VIEWER)
            )
        if view.basename == "vehicle":
            return request.method in {"GET", "HEAD", "OPTIONS"} and (
                has_role(request.user, TECHNICIAN) or has_role(request.user, READ_ONLY_VIEWER)
            )
        if view.basename == "service-record":
            if has_role(request.user, TECHNICIAN):
                return request.method in {"GET", "HEAD", "OPTIONS", "POST"}
            return has_role(request.user, READ_ONLY_VIEWER) and request.method in {"GET", "HEAD", "OPTIONS"}
        if view.basename == "reading":
            if has_role(request.user, TECHNICIAN):
                return request.method in {"GET", "HEAD", "OPTIONS", "POST"}
            return has_role(request.user, READ_ONLY_VIEWER) and request.method in {"GET", "HEAD", "OPTIONS"}
        return False


class MaintenanceStatusPermission(BasePermission):
    message = "An authenticated fleet role is required."

    def has_permission(self, request, view):
        return request.user.is_authenticated and any(
            has_role(request.user, role) for role in (FLEET_MANAGER, TECHNICIAN, READ_ONLY_VIEWER)
        )
