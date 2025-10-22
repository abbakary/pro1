import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404, JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    ExamPaper, Driver, Submission, ExamDistribution,
    MarkedExamSubmission, AuditHistory
)
from .pdf_utils import PDFMarker


@staff_member_required
def mark_exam_paper(request, exam_id: int, driver_id: int):
    """
    Manual exam marking interface with PDF viewer and scoring.
    No automatic question detection - staff manually review and score the exam.
    """
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver = get_object_or_404(Driver, pk=driver_id)

    if not ExamDistribution.objects.filter(exam=exam, driver=driver).exists():
        raise Http404("Driver not assigned to this exam")

    submission = Submission.objects.filter(exam=exam, driver=driver).first()
    if not submission:
        raise Http404("No submission found for this driver-exam pair")

    if request.method == 'POST':
        score_str = request.POST.get('score', '').strip()
        notes = request.POST.get('notes', '').strip()

        try:
            score = Decimal(score_str) if score_str else None

            if score is not None and score < 0:
                messages.error(request, "Score cannot be negative")
                return redirect('trainingapp:mark_exam_paper', exam_id=exam_id, driver_id=driver_id)

            if score is not None and score > exam.total_marks:
                messages.error(request, f"Score cannot exceed {exam.total_marks}")
                return redirect('trainingapp:mark_exam_paper', exam_id=exam_id, driver_id=driver_id)

            submission.score = score
            submission.notes = notes
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()

            ExamDistribution.objects.filter(exam=exam, driver=driver).update(status='scored')

            AuditHistory.objects.create(
                action='mark_exam',
                entity_type='Submission',
                entity_id=str(submission.id),
                user=request.user,
                details={
                    'exam_id': exam.id,
                    'driver_id': driver.id,
                    'score': float(score) if score else None,
                    'total_marks': exam.total_marks,
                },
            )

            messages.success(request, f"Exam marked with score {score}/{exam.total_marks}")
            return redirect('trainingapp:submission_list', exam_id=exam_id)

        except ValueError:
            messages.error(request, "Invalid score format")
            return redirect('trainingapp:mark_exam_paper', exam_id=exam_id, driver_id=driver_id)

    marked_submission = MarkedExamSubmission.objects.filter(submission=submission).first()

    return render(request, 'exams/mark_exam_paper.html', {
        'exam': exam,
        'driver': driver,
        'submission': submission,
        'marked_submission': marked_submission,
    })


@staff_member_required
def download_marked_pdf(request, submission_id: int):
    """
    Download the marked PDF file.
    """
    submission = get_object_or_404(Submission, pk=submission_id)
    marked_submission = get_object_or_404(MarkedExamSubmission, submission=submission)

    if not marked_submission.marked_pdf_file:
        raise Http404("Marked PDF not found")

    file_path = marked_submission.marked_pdf_file.path

    if not os.path.exists(file_path):
        raise Http404("PDF file not found on disk")

    response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
    filename = f"marked_{submission.driver.first_name}_{submission.exam.title}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


@login_required
def driver_submissions(request, driver_id: int):
    """
    Display all submissions and marked PDFs for a specific driver.
    Staff can view any driver's submissions, drivers can only view their own.
    """
    driver = get_object_or_404(Driver, pk=driver_id)

    # Check if the logged-in user is viewing their own submissions or is staff
    if not request.user.is_staff:
        user_driver = getattr(request.user, 'driver_profile', None)
        if user_driver != driver:
            raise Http404("You do not have permission to view this driver's submissions")

    submissions = Submission.objects.filter(driver=driver).select_related('exam').order_by('-created_at')

    submissions_with_marks = []
    for sub in submissions:
        marked_sub = MarkedExamSubmission.objects.filter(submission=sub).first()

        submissions_with_marks.append({
            'submission': sub,
            'marked_submission': marked_sub,
            'is_marked': sub.score is not None,
            'can_download': marked_sub and marked_sub.is_generated and marked_sub.marked_pdf_file,
        })

    return render(request, 'exams/driver_submissions.html', {
        'driver': driver,
        'submissions_with_marks': submissions_with_marks,
    })


@login_required
def view_marked_submission(request, submission_id: int):
    """
    View a marked exam submission with PDF viewer.
    Drivers can only view their own submissions.
    """
    submission = get_object_or_404(Submission, pk=submission_id)

    # Check permissions - user must be staff or the submission owner (driver)
    if not request.user.is_staff:
        user_driver = getattr(request.user, 'driver_profile', None)
        if user_driver != submission.driver:
            raise Http404("You do not have permission to view this submission")

    marked_submission = MarkedExamSubmission.objects.filter(submission=submission).first()

    if not marked_submission or not marked_submission.is_generated:
        return render(request, 'exams/marked_submission_viewer.html', {
            'submission': submission,
            'marked_submission': marked_submission,
            'error': 'This exam paper has not been marked yet.',
        }, status=404)

    return render(request, 'exams/marked_submission_viewer.html', {
        'submission': submission,
        'marked_submission': marked_submission,
    })
