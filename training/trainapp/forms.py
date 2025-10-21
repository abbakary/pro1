from django import forms
from django.contrib.auth import get_user_model
from .models import Driver, Batch, ExamPaper, Submission, TimetableEntry, Notification, NotificationResponse, QuestionAnswer

User = get_user_model()

class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ["first_name", "last_name", "phone", "license_no", "company", "batch", "profile_photo", "user"]

class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["name", "start_date", "end_date", "description"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

class ExamUploadForm(forms.ModelForm):
    class Meta:
        model = ExamPaper
        fields = ["title", "batch", "file", "total_marks"]

class ScoreForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["scanned_file", "score", "notes"]
        widgets = {
            "score": forms.NumberInput(attrs={"step": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

class TimetableEntryForm(forms.ModelForm):
    class Meta:
        model = TimetableEntry
        fields = ["title", "starts_at", "ends_at", "batch", "driver", "location", "notes"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ["title", "body", "attachment", "batch", "driver"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        cleaned = super().clean()
        batch = cleaned.get("batch")
        driver = cleaned.get("driver")
        if not batch and not driver:
            raise forms.ValidationError("Select a Batch or a Driver to send notification.")
        if batch and driver:
            raise forms.ValidationError("Choose either Batch or Driver, not both.")
        return cleaned

class NotificationResponseForm(forms.ModelForm):
    class Meta:
        model = NotificationResponse
        fields = ["message"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3, "placeholder": "Write your response..."}),
        }
