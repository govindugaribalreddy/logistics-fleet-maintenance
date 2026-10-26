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
