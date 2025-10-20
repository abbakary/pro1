from django import forms
from django.contrib.auth import get_user_model
from .models import Driver, Batch, ExamPaper, Submission, TimetableEntry

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
