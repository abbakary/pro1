from django.contrib import admin
from .models import Driver, Batch, ExamPaper, ExamDistribution, Submission, AuditHistory, TimetableEntry, Notification, NotificationReceipt, NotificationResponse

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "phone", "license_no", "company", "batch", "created_at")
    list_filter = ("batch", "company")
    search_fields = ("first_name", "last_name", "phone", "license_no")

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "created_at")
    search_fields = ("name",)

@admin.register(ExamPaper)
class ExamPaperAdmin(admin.ModelAdmin):
    list_display = ("title", "batch", "total_marks", "created_by", "created_at")
    list_filter = ("batch",)
    search_fields = ("title",)

@admin.register(ExamDistribution)
class ExamDistributionAdmin(admin.ModelAdmin):
    list_display = ("exam", "driver", "status", "created_at")
    list_filter = ("status", "exam__batch")
    search_fields = ("exam__title", "driver__first_name", "driver__last_name")

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("exam", "driver", "score", "graded_by", "graded_at", "created_at")
    list_filter = ("graded_at",)
    search_fields = ("exam__title", "driver__first_name", "driver__last_name")

@admin.register(AuditHistory)
class AuditHistoryAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "entity_id", "user", "created_at")
    search_fields = ("action", "entity_type", "entity_id")

@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "starts_at", "ends_at", "batch", "driver", "created_at")
    list_filter = ("batch",)
    search_fields = ("title", "location", "notes")

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "target_display", "created_by", "created_at")
    search_fields = ("title", "body")
    list_filter = ("batch",)

@admin.register(NotificationReceipt)
class NotificationReceiptAdmin(admin.ModelAdmin):
    list_display = ("notification", "driver", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("notification__title", "driver__first_name", "driver__last_name")

@admin.register(NotificationResponse)
class NotificationResponseAdmin(admin.ModelAdmin):
    list_display = ("receipt", "created_at")
    search_fields = ("message",)
