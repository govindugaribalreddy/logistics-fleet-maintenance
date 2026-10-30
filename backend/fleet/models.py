from datetime import timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone


class Vehicle(models.Model):
    class OperationalStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        IN_MAINTENANCE = "in_maintenance", "In maintenance"
        RETIRED = "retired", "Retired"

    vehicle_identifier = models.CharField(max_length=50, unique=True)
    vin = models.CharField(max_length=17, unique=True)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1886), MaxValueValidator(2100)])
    license_plate = models.CharField(max_length=20, unique=True)
    mileage = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    engine_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    operational_status = models.CharField(max_length=20, choices=OperationalStatus.choices, default=OperationalStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["vehicle_identifier"]
        indexes = [
            models.Index(fields=["operational_status"]),
            models.Index(fields=["make", "model"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(mileage__gte=0), name="vehicle_mileage_nonnegative"),
            models.CheckConstraint(condition=models.Q(engine_hours__gte=0), name="vehicle_engine_hours_nonnegative"),
        ]

    def __str__(self):
        return self.vehicle_identifier


class VehicleReading(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        SERVICE_RECORD = "service_record", "Service record"
        TELEMATICS = "telematics", "Telematics"
        IMPORT = "import", "Import"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="readings")
    recorded_at = models.DateTimeField(default=timezone.now)
    mileage = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    engine_hours = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(fields=["vehicle", "-recorded_at"]),
            models.Index(fields=["source", "-recorded_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(mileage__gte=0), name="reading_mileage_nonnegative"),
            models.CheckConstraint(condition=models.Q(engine_hours__gte=0), name="reading_engine_hours_nonnegative"),
        ]

    @classmethod
    def record(cls, *, vehicle_id, mileage, engine_hours, source=Source.MANUAL, recorded_at=None):
        """Accept a reading and update the vehicle snapshot atomically."""
        with transaction.atomic():
            vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
            if mileage < vehicle.mileage or engine_hours < vehicle.engine_hours:
                raise ValidationError("Accepted vehicle readings cannot decrease.")
            reading = cls.objects.create(
                vehicle=vehicle,
                mileage=mileage,
                engine_hours=engine_hours,
                source=source,
                recorded_at=recorded_at or timezone.now(),
            )
            Vehicle.objects.filter(pk=vehicle.pk).update(
                mileage=mileage,
                engine_hours=engine_hours,
                updated_at=timezone.now(),
            )
            return reading

    def __str__(self):
        return f"{self.vehicle} @ {self.recorded_at.isoformat()}"


class Technician(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)
    skills = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["active", "name"])]

    def __str__(self):
        return self.name


class MaintenanceType(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    mileage_interval = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    engine_hour_interval = models.DecimalField(null=True, blank=True, max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    calendar_interval_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(mileage_interval__isnull=True) | models.Q(mileage_interval__gt=0), name="maintenance_mileage_interval_positive"),
            models.CheckConstraint(condition=models.Q(engine_hour_interval__isnull=True) | models.Q(engine_hour_interval__gt=0), name="maintenance_engine_interval_positive"),
            models.CheckConstraint(condition=models.Q(calendar_interval_days__isnull=True) | models.Q(calendar_interval_days__gt=0), name="maintenance_calendar_interval_positive"),
        ]

    def __str__(self):
        return self.name


class MaintenancePlan(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="maintenance_plans")
    maintenance_type = models.ForeignKey(MaintenanceType, on_delete=models.PROTECT, related_name="vehicle_plans")
    mileage_interval = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    engine_hour_interval = models.DecimalField(null=True, blank=True, max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    calendar_interval_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    enabled = models.BooleanField(default=True)
    baseline_mileage = models.PositiveIntegerField(null=True, blank=True, editable=False)
    baseline_engine_hours = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    baseline_date = models.DateField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["vehicle", "maintenance_type"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle", "maintenance_type"], name="unique_vehicle_maintenance_plan"),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(mileage_interval__isnull=True)
                        | models.Q(mileage_interval__gt=0)
                    )
                    & (
                        models.Q(engine_hour_interval__isnull=True)
                        | models.Q(engine_hour_interval__gt=0)
                    )
                    & (
                        models.Q(calendar_interval_days__isnull=True)
                        | models.Q(calendar_interval_days__gt=0)
                    )
                    & ~models.Q(
                        mileage_interval__isnull=True,
                        engine_hour_interval__isnull=True,
                        calendar_interval_days__isnull=True,
                    )
                ),
                name="maintenance_plan_has_schedule_basis",
            ),
        ]
        indexes = [
            models.Index(fields=["vehicle", "enabled"]),
            models.Index(fields=["maintenance_type", "enabled"]),
        ]

    def clean(self):
        super().clean()
        if not any((self.mileage_interval, self.engine_hour_interval, self.calendar_interval_days)):
            raise ValidationError("At least one positive scheduling interval is required.")
        for field in ("mileage_interval", "engine_hour_interval", "calendar_interval_days"):
            value = getattr(self, field)
            if value is not None and value <= 0:
                raise ValidationError({field: "Scheduling intervals must be positive."})

    def save(self, *args, **kwargs):
        if self.baseline_mileage is None or self.baseline_engine_hours is None or self.baseline_date is None:
            vehicle = self.vehicle if self.vehicle_id else None
            if vehicle is not None:
                self.baseline_mileage = vehicle.mileage
                self.baseline_engine_hours = vehicle.engine_hours
            self.baseline_date = self.baseline_date or timezone.localdate()
        super().save(*args, **kwargs)

    @property
    def latest_completed_service(self):
        from .maintenance_status import _latest_service
        return _latest_service(self)

    @property
    def next_due_mileage(self):
        from .maintenance_status import classify_plan
        return classify_plan(self)["next_due_mileage"]

    @property
    def next_due_engine_hours(self):
        from .maintenance_status import classify_plan
        return classify_plan(self)["next_due_engine_hours"]

    @property
    def next_due_date(self):
        from .maintenance_status import classify_plan
        return classify_plan(self)["next_due_date"]

    @property
    def is_due(self):
        from .maintenance_status import classify_plan
        return classify_plan(self)["status"] in {"overdue", "due_now", "due_soon"}


class ServiceRecord(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="service_records")
    service_date = models.DateField()
    service_type = models.ForeignKey(MaintenanceType, on_delete=models.PROTECT, related_name="service_records")
    description = models.TextField(blank=True)
    mileage = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    engine_hours = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_records")
    parts_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]
        indexes = [
            models.Index(fields=["vehicle", "service_date"]),
            models.Index(fields=["service_type", "service_date"]),
            models.Index(fields=["technician", "service_date"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(mileage__gte=0), name="service_mileage_nonnegative"),
            models.CheckConstraint(condition=models.Q(engine_hours__gte=0), name="service_engine_hours_nonnegative"),
            models.CheckConstraint(condition=models.Q(parts_cost__gte=0), name="service_parts_cost_nonnegative"),
            models.CheckConstraint(condition=models.Q(labor_cost__gte=0), name="service_labor_cost_nonnegative"),
            models.CheckConstraint(condition=models.Q(total_cost__gte=0), name="service_total_cost_nonnegative"),
        ]

    def __str__(self):
        return f"{self.vehicle} - {self.service_date} - {self.service_type}"

    def save(self, *args, **kwargs):
        self.total_cost = self.parts_cost + self.labor_cost
        super().save(*args, **kwargs)


class WorkOrder(models.Model):
    class Category(models.TextChoices):
        PREVENTIVE = "preventive", "Preventive"
        CORRECTIVE = "corrective", "Corrective"
        INSPECTION = "inspection", "Inspection"
        EMERGENCY = "emergency", "Emergency"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        WAITING_FOR_PARTS = "waiting_for_parts", "Waiting for parts"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    VALID_TRANSITIONS = {
        Status.OPEN: {Status.ASSIGNED, Status.CANCELLED},
        Status.ASSIGNED: {Status.OPEN, Status.IN_PROGRESS, Status.CANCELLED},
        Status.IN_PROGRESS: {Status.WAITING_FOR_PARTS, Status.COMPLETED, Status.CANCELLED},
        Status.WAITING_FOR_PARTS: {Status.IN_PROGRESS, Status.CANCELLED},
        Status.COMPLETED: set(),
        Status.CANCELLED: set(),
    }

    work_order_number = models.CharField(max_length=50, unique=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="work_orders")
    maintenance_plan = models.ForeignKey(MaintenancePlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_orders")
    assigned_technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_work_orders")
    category = models.CharField(max_length=20, choices=Category.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    problem_description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    reported_date = models.DateField(default=timezone.localdate)
    target_completion_date = models.DateField(null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-reported_date", "-created_at"]
        indexes = [
            models.Index(fields=["vehicle", "status"]),
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["target_completion_date", "status"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(estimated_cost__gte=0), name="work_order_estimated_cost_nonnegative"),
        ]

    def clean(self):
        super().clean()
        if not self.problem_description or not self.problem_description.strip():
            raise ValidationError({"problem_description": "A problem description is required."})
        if self.target_completion_date and self.target_completion_date < self.reported_date:
            raise ValidationError({"target_completion_date": "Target completion cannot be before the reported date."})
        if self.maintenance_plan_id and self.maintenance_plan.vehicle_id != self.vehicle_id:
            raise ValidationError({"maintenance_plan": "The maintenance plan must belong to the selected vehicle."})
        if self.assigned_technician_id and not self.assigned_technician.active:
            raise ValidationError({"assigned_technician": "Only active technicians can be assigned."})

    def can_transition_to(self, new_status):
        return new_status == self.status or new_status in self.VALID_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status):
        if not self.can_transition_to(new_status):
            raise ValidationError({"status": f"Cannot transition from {self.status} to {new_status}."})
        self.status = new_status

    def assign_to(self, technician, acting_user):
        """Assign or reassign under a row lock and write one immutable history row."""
        if technician is not None and not technician.active:
            raise ValidationError({"assigned_technician": "Only active technicians can be assigned."})
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            previous_id = locked.assigned_technician_id
            new_id = technician.id if technician else None
            if previous_id == new_id:
                return locked
            type(self).objects.filter(pk=locked.pk).update(assigned_technician_id=new_id, updated_at=timezone.now())
            WorkOrderAssignmentHistory.objects.create(
                work_order=locked,
                previous_technician_id=previous_id,
                new_technician_id=new_id,
                acting_user=acting_user,
            )
            self.assigned_technician_id = new_id
            return self

    def save(self, *args, **kwargs):
        if self.pk:
            previous_status = type(self).objects.only("status").get(pk=self.pk).status
            if previous_status != self.status:
                if self.status not in self.VALID_TRANSITIONS.get(previous_status, set()):
                    raise ValidationError({"status": f"Cannot transition from {previous_status} to {self.status}."})
        super().save(*args, **kwargs)

    def __str__(self):
        return self.work_order_number


class WorkOrderAssignmentHistory(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="assignment_history")
    previous_technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="previous_work_order_assignments")
    new_technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="new_work_order_assignments")
    acting_user = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="work_order_assignment_changes")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "id"]
        indexes = [
            models.Index(fields=["work_order", "changed_at"]),
            models.Index(fields=["new_technician", "changed_at"]),
        ]
