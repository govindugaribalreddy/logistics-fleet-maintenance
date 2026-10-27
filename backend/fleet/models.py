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

    @property
    def latest_completed_service(self):
        return self.vehicle.service_records.filter(service_type=self.maintenance_type).order_by("-service_date", "-created_at").first()

    @property
    def next_due_mileage(self):
        if self.mileage_interval is None:
            return None
        baseline = self.latest_completed_service
        return (baseline.mileage if baseline else self.vehicle.mileage) + self.mileage_interval

    @property
    def next_due_engine_hours(self):
        if self.engine_hour_interval is None:
            return None
        baseline = self.latest_completed_service
        return (baseline.engine_hours if baseline else self.vehicle.engine_hours) + self.engine_hour_interval

    @property
    def next_due_date(self):
        if self.calendar_interval_days is None:
            return None
        baseline = self.latest_completed_service
        baseline_date = baseline.service_date if baseline else self.created_at.date()
        return baseline_date + timedelta(days=self.calendar_interval_days)

    @property
    def is_due(self):
        if not self.enabled:
            return False
        due = False
        if self.next_due_mileage is not None:
            due = due or self.vehicle.mileage >= self.next_due_mileage
        if self.next_due_engine_hours is not None:
            due = due or self.vehicle.engine_hours >= self.next_due_engine_hours
        if self.next_due_date is not None:
            due = due or timezone.localdate() >= self.next_due_date
        return due


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
