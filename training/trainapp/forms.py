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


class QuestionAnswerForm(forms.ModelForm):
    class Meta:
        model = QuestionAnswer
        fields = ["is_correct", "notes"]
        widgets = {
            "is_correct": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "form-control", "placeholder": "Optional notes..."}),
        }


class QuestionAnswerFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        question_numbers = set()
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                question_num = form.cleaned_data.get('question_number')
                if question_num:
                    if question_num in question_numbers:
                        raise forms.ValidationError("Duplicate question number")
                    question_numbers.add(question_num)
