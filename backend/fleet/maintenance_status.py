from datetime import date, timedelta
from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from .models import MaintenancePlan, ServiceRecord


STATUS_OVERDUE = "overdue"
STATUS_DUE_NOW = "due_now"
STATUS_DUE_SOON = "due_soon"
STATUS_NOT_YET_DUE = "not_yet_due"


def _latest_service(plan):
    cached = getattr(plan.vehicle, "_prefetched_objects_cache", {}).get("service_records")
    if cached is not None:
        return next((record for record in cached if record.service_type_id == plan.maintenance_type_id), None)
    return plan.vehicle.service_records.filter(service_type=plan.maintenance_type).order_by("-service_date", "-created_at").first()


def classify_plan(plan, *, now=None, upcoming_days=None, upcoming_mileage=None, upcoming_engine_hours=None):
    now = now or timezone.now()
    local_today = timezone.localtime(now).date()
    upcoming_days = settings.MAINTENANCE_UPCOMING_DAYS if upcoming_days is None else upcoming_days
    upcoming_mileage = settings.MAINTENANCE_UPCOMING_MILEAGE if upcoming_mileage is None else upcoming_mileage
    upcoming_engine_hours = settings.MAINTENANCE_UPCOMING_ENGINE_HOURS if upcoming_engine_hours is None else upcoming_engine_hours
    service = _latest_service(plan)
    vehicle = plan.vehicle
    criteria = []

    if plan.mileage_interval is not None:
        baseline = service.mileage if service else plan.baseline_mileage
        due = baseline + plan.mileage_interval if baseline is not None else None
        criteria.append({"criterion": "mileage", "current": vehicle.mileage, "due": due, "missing": due is None})
    if plan.engine_hour_interval is not None:
        baseline = service.engine_hours if service else plan.baseline_engine_hours
        due = baseline + plan.engine_hour_interval if baseline is not None else None
        criteria.append({"criterion": "engine_hours", "current": vehicle.engine_hours, "due": due, "missing": due is None})
    if plan.calendar_interval_days is not None:
        baseline = service.service_date if service else plan.baseline_date
        due = baseline + timedelta(days=plan.calendar_interval_days) if baseline else None
        criteria.append({"criterion": "calendar", "current": local_today, "due": due, "missing": due is None})

    evaluated = [criterion for criterion in criteria if not criterion["missing"]]
    overdue = []
    due_now = []
    due_soon = []
    for criterion in evaluated:
        current = criterion["current"]
        due = criterion["due"]
        if current > due:
            overdue.append(criterion["criterion"])
        elif current == due:
            due_now.append(criterion["criterion"])
        elif criterion["criterion"] == "mileage" and due - current <= upcoming_mileage:
            due_soon.append(criterion["criterion"])
        elif criterion["criterion"] == "engine_hours" and due - current <= upcoming_engine_hours:
            due_soon.append(criterion["criterion"])
        elif criterion["criterion"] == "calendar" and due - current <= timedelta(days=upcoming_days):
            due_soon.append(criterion["criterion"])

    if not plan.enabled:
        status = STATUS_NOT_YET_DUE
    elif overdue:
        status = STATUS_OVERDUE
    elif due_now:
        status = STATUS_DUE_NOW
    elif due_soon:
        status = STATUS_DUE_SOON
    else:
        status = STATUS_NOT_YET_DUE

    return {
        "plan": plan,
        "vehicle": vehicle,
        "maintenance_type": plan.maintenance_type,
        "status": status,
        "criteria": criteria,
        "due_criteria": overdue + due_now + due_soon,
        "latest_service": service,
        "next_due_mileage": next((item["due"] for item in criteria if item["criterion"] == "mileage"), None),
        "next_due_engine_hours": next((item["due"] for item in criteria if item["criterion"] == "engine_hours"), None),
        "next_due_date": next((item["due"] for item in criteria if item["criterion"] == "calendar"), None),
        "evaluated_at": now,
    }


def maintenance_plan_queryset():
    service_records = ServiceRecord.objects.order_by("-service_date", "-created_at").select_related("service_type")
    return MaintenancePlan.objects.filter(enabled=True).select_related("vehicle", "maintenance_type").prefetch_related(
        Prefetch("vehicle__service_records", queryset=service_records)
    )


def classify_plans(plans, **kwargs):
    return [classify_plan(plan, **kwargs) for plan in plans]
