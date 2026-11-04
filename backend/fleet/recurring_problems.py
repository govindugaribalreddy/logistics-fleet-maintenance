from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import DowntimeRecord, WorkOrder, WorkOrderExpense


DEFAULT_WINDOW_DAYS = 365


def analyze_recurring_problems(*, vehicle_id=None, days=DEFAULT_WINDOW_DAYS, today=None):
    end_date = today or timezone.localdate()
    start_date = end_date - timedelta(days=days)
    orders = list(
        WorkOrder.objects.select_related("vehicle")
        .filter(reported_date__gte=start_date, reported_date__lte=end_date)
        .filter(**({"vehicle_id": vehicle_id} if vehicle_id is not None else {}))
        .order_by("vehicle_id", "category", "reported_date", "id")
    )
    groups = {}
    for order in orders:
        key = (order.vehicle_id, order.category)
        group = groups.setdefault(key, {
            "vehicle": order.vehicle,
            "category": order.category,
            "work_orders": [],
            "order_ids": [],
        })
        group["work_orders"].append(order)
        group["order_ids"].append(order.id)

    all_order_ids = [order.id for order in orders]
    expenses = WorkOrderExpense.objects.filter(
        work_order_id__in=all_order_ids,
        expense_date__gte=start_date,
        expense_date__lte=end_date,
    ) if all_order_ids else WorkOrderExpense.objects.none()
    expense_totals = {}
    for expense in expenses:
        expense_totals[expense.work_order_id] = expense_totals.get(expense.work_order_id, Decimal("0.00")) + expense.total

    window_start = timezone.make_aware(datetime.combine(start_date, time.min))
    window_end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    downtime = DowntimeRecord.objects.filter(
        work_order_id__in=all_order_ids,
        start_time__lt=window_end,
    ) if all_order_ids else DowntimeRecord.objects.none()
    downtime_seconds = {}
    for record in downtime:
        interval_end = min(record.end_time or timezone.now(), window_end)
        interval_start = max(record.start_time, window_start)
        if interval_end > interval_start:
            downtime_seconds[record.work_order_id] = downtime_seconds.get(record.work_order_id, 0) + int((interval_end - interval_start).total_seconds())

    results = []
    for group in groups.values():
        related = group["work_orders"]
        total_expenses = sum((expense_totals.get(order.id, Decimal("0.00")) for order in related), Decimal("0.00")).quantize(Decimal("0.01"))
        total_downtime = sum((downtime_seconds.get(order.id, 0) for order in related), 0)
        results.append({
            "vehicle_id": group["vehicle"].id,
            "vehicle_identifier": group["vehicle"].vehicle_identifier,
            "issue_category": group["category"],
            "repeat_repair_count": len(related),
            "work_order_ids": group["order_ids"],
            "total_repair_expenses": total_expenses,
            "downtime_seconds": total_downtime,
            "window_start": start_date,
            "window_end": end_date,
        })
    return results
