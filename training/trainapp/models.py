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


class Notification(TimeStampedModel):
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    attachment = models.FileField(upload_to='notifications/', blank=True)
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def target_display(self) -> str:
        if self.driver:
            return str(self.driver)
        if self.batch:
            return f"Batch: {self.batch.name}"
        return "All"

    def __str__(self) -> str:
        return self.title


class NotificationReceipt(TimeStampedModel):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='receipts')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='notification_receipts')
    is_read = models.BooleanField(default=False)

    class Meta:
        unique_together = ('notification', 'driver')

    def __str__(self) -> str:
        return f"{self.notification.title} -> {self.driver.first_name}"


class NotificationResponse(TimeStampedModel):
    receipt = models.ForeignKey(NotificationReceipt, on_delete=models.CASCADE, related_name='responses')
    message = models.TextField()

    def __str__(self) -> str:
        return f"Response to {self.receipt.notification.title} by {self.receipt.driver.first_name}"


class ExamTemplate(TimeStampedModel):
    exam = models.OneToOneField(ExamPaper, on_delete=models.CASCADE, related_name='template')
    original_file = models.FileField(upload_to='exam_templates/')
    question_mapping = models.JSONField(default=dict, blank=True, help_text="Stores question positions detected from PDF")
    is_processed = models.BooleanField(default=False, help_text="Whether question detection has been completed")
    detected_question_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Exam Template'
        verbose_name_plural = 'Exam Templates'

    def __str__(self) -> str:
        return f"Template for {self.exam.title}"


class QuestionAnswer(TimeStampedModel):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='question_answers')
    question_number = models.PositiveIntegerField()
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Marks obtained for this question (for weighted scoring)"
    )
    marks_total = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        help_text="Total marks for this question (if weighted scoring is used)"
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('submission', 'question_number')
        ordering = ['question_number']

    def __str__(self) -> str:
        return f"Q{self.question_number} - {self.submission.driver} - {'✓' if self.is_correct else '✗'} ({self.marks_obtained}/{self.marks_total})"

    def get_percentage_score(self) -> float:
        """Calculate percentage score for this question"""
        if self.marks_total == 0:
            return 0.0
        return round((float(self.marks_obtained) / float(self.marks_total)) * 100, 2)


class MarkedExamSubmission(TimeStampedModel):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name='marked_version')
    marked_pdf_file = models.FileField(upload_to='marked_submissions/', blank=True)
    total_correct = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    total_marks_obtained = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Total marks obtained (for weighted scoring)"
    )
    total_marks_available = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Total marks available (for weighted scoring)"
    )
    is_weighted_scoring = models.BooleanField(
        default=False,
        help_text="Whether this exam uses weighted scoring (per-question marks)"
    )
    is_generated = models.BooleanField(default=False)
    generation_error = models.TextField(blank=True)

    def get_percentage_score(self) -> float:
        """Calculate percentage score based on marking mode"""
        if self.is_weighted_scoring:
            if self.total_marks_available == 0:
                return 0.0
            return round((float(self.total_marks_obtained) / float(self.total_marks_available)) * 100, 2)
        else:
            if self.total_questions == 0:
                return 0.0
            return round((self.total_correct / self.total_questions) * 100, 2)

    class Meta:
        verbose_name = 'Marked Exam Submission'
        verbose_name_plural = 'Marked Exam Submissions'

    def __str__(self) -> str:
        return f"Marked: {self.submission.driver} - {self.submission.exam}"
