from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Batch(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class Driver(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='driver_profile')
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    license_no = models.CharField(max_length=64, blank=True)
    company = models.CharField(max_length=120, blank=True)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, related_name='drivers')
    profile_photo = models.ImageField(upload_to='driver_photos/', blank=True)

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class ExamPaper(TimeStampedModel):
    title = models.CharField(max_length=200)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams')
    file = models.FileField(upload_to='exam_papers/')
    total_marks = models.PositiveIntegerField(default=100)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return self.title


class ExamDistribution(TimeStampedModel):
    STATUS_CHOICES = (
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
        ('scored', 'Scored'),
    )
    exam = models.ForeignKey(ExamPaper, on_delete=models.CASCADE, related_name='distributions')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='distributions')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='assigned')

    class Meta:
        unique_together = ('exam', 'driver')

    def __str__(self) -> str:
        return f"{self.exam} -> {self.driver} ({self.status})"


class Submission(TimeStampedModel):
    exam = models.ForeignKey(ExamPaper, on_delete=models.CASCADE, related_name='submissions')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='submissions')
    scanned_file = models.FileField(upload_to='submissions/', blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('exam', 'driver')

    def mark_scored(self, user):
        self.graded_by = user
        self.graded_at = timezone.now()
        self.save(update_fields=['graded_by', 'graded_at', 'updated_at'])
        ExamDistribution.objects.filter(exam=self.exam, driver=self.driver).update(status='scored')

    def __str__(self) -> str:
        return f"Submission: {self.driver} - {self.exam}"


class AuditHistory(TimeStampedModel):
    action = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=120)
    entity_id = models.CharField(max_length=120)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type} {self.entity_id}"


class TimetableEntry(TimeStampedModel):
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, null=True, blank=True, related_name='timetable_entries')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, null=True, blank=True, related_name='timetable_entries')
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return self.title
