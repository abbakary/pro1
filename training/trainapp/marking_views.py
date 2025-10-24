import json
import os
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    ExamPaper, Driver, Submission, ExamDistribution, Batch,
    MarkedExamSubmission, AuditHistory, QuestionAnswer, ExamTemplate
)
from .pdf_utils import PDFMarker, detect_questions_in_pdf, mark_pdf_submission
from .forms import FastExamMarkingForm


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

    submission, created = Submission.objects.get_or_create(exam=exam, driver=driver)

    if request.method == 'POST':
        score_str = request.POST.get('score', '').strip()
        notes = request.POST.get('notes', '').strip()

        try:
            score = Decimal(score_str) if score_str else None

            if score is not None and score < 0:
                messages.error(request, "Score cannot be negative")
                return redirect('trainapp:mark_exam_paper', exam_id=exam_id, driver_id=driver_id)

            if score is not None and score > exam.total_marks:
                messages.error(request, f"Score cannot exceed {exam.total_marks}")
                return redirect('trainapp:mark_exam_paper', exam_id=exam_id, driver_id=driver_id)

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
            return redirect('trainapp:submission_list', exam_id=exam_id)

        except ValueError:
            messages.error(request, "Invalid score format")
            return redirect('trainapp:mark_exam_paper', exam_id=exam_id, driver_id=driver_id)

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

    submissions = Submission.objects.filter(driver=driver).select_related('exam').prefetch_related('question_answers').order_by('-created_at')

    submissions_with_marks = []
    for sub in submissions:
        marked_sub = MarkedExamSubmission.objects.filter(submission=sub).first()

        submissions_with_marks.append({
            'submission': sub,
            'marked_submission': marked_sub,
            'is_marked': sub.score is not None,
            'can_download': marked_sub and marked_sub.is_generated and marked_sub.marked_pdf_file,
            'question_count': sub.question_answers.count(),
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


@staff_member_required
@transaction.atomic
def fast_mark_exam(request, exam_id: int, driver_id: int):
    """
    Fast marking interface with flexible input modes and auto question detection.
    Supports marking via total marks (auto-distribute) or per-question marking.
    """
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver = get_object_or_404(Driver, pk=driver_id)

    if not ExamDistribution.objects.filter(exam=exam, driver=driver).exists():
        raise Http404("Driver not assigned to this exam")

    submission, created = Submission.objects.get_or_create(exam=exam, driver=driver)

    question_mapping = {}
    detected_questions = []
    detection_error = None

    try:
        if exam.file:
            pdf_path = exam.file.path
            if os.path.exists(pdf_path):
                question_mapping, detected_count = detect_questions_in_pdf(pdf_path)
                detected_questions = sorted([int(q) for q in question_mapping.keys()])
    except Exception as e:
        detection_error = f"Could not auto-detect questions: {str(e)}"

    if request.method == 'POST':
        form = FastExamMarkingForm(request.POST)
        if form.is_valid():
            marking_mode = form.cleaned_data.get('marking_mode')
            total_marks_input = form.cleaned_data.get('total_marks_input')
            equal_weight = form.cleaned_data.get('equal_weight')
            notes = form.cleaned_data.get('notes')

            question_marks = {}
            marks_by_question = {}
            correct_questions = []

            if marking_mode == 'total_marks':
                score = total_marks_input
                submission.score = score
                submission.notes = notes
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
                submission.save()

                ExamDistribution.objects.filter(exam=exam, driver=driver).update(status='scored')

                marked_submission, _ = MarkedExamSubmission.objects.get_or_create(submission=submission)
                marked_submission.total_questions = len(detected_questions) if detected_questions else 1
                marked_submission.total_correct = int(score)
                marked_submission.save()

                try:
                    if exam.file and os.path.exists(exam.file.path) and question_mapping:
                        marked_pdf_filename = f"marked_{submission.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                        marked_pdf_dir = os.path.join(str(settings.MEDIA_ROOT), 'marked_submissions')
                        os.makedirs(marked_pdf_dir, exist_ok=True)
                        marked_pdf_path = os.path.join(marked_pdf_dir, marked_pdf_filename)

                        marks_by_question = {str(i): False for i in detected_questions}
                        for i in range(int(score)):
                            if i < len(detected_questions):
                                marks_by_question[str(detected_questions[i])] = True

                        mark_pdf_submission(
                            source_pdf=exam.file.path,
                            output_pdf=marked_pdf_path,
                            driver_name=f"{driver.first_name} {driver.last_name}",
                            exam_title=exam.title,
                            marks=marks_by_question,
                            question_mapping=question_mapping,
                            exam_date=submission.created_at.strftime('%d-%m-%Y')
                        )

                        marked_submission.marked_pdf_file = f"marked_submissions/{marked_pdf_filename}"
                        marked_submission.is_generated = True
                        marked_submission.generation_error = ''
                        marked_submission.save()
                except Exception as e:
                    marked_submission.is_generated = False
                    marked_submission.generation_error = str(e)
                    marked_submission.save()

                AuditHistory.objects.create(
                    action='fast_mark_exam_total',
                    entity_type='Submission',
                    entity_id=str(submission.id),
                    user=request.user,
                    details={
                        'exam_id': exam.id,
                        'driver_id': driver.id,
                        'score': float(score),
                        'total_marks': exam.total_marks,
                        'mode': 'total_marks',
                    },
                )

                messages.success(request, f"Exam marked with score {score}/{exam.total_marks}. View the marked document below.")
                return redirect('trainapp:view_marked_submission', submission_id=submission.id)

            elif marking_mode == 'per_question':
                if not detected_questions:
                    messages.error(request, "No questions detected in exam. Please mark questions manually or enter total marks.")
                    return redirect('trainapp:fast_mark_exam', exam_id=exam_id, driver_id=driver_id)

                correct_questions = []
                total_questions = len(detected_questions)

                for question_id in detected_questions:
                    # Question ID may contain letters (e.g., "1a", "1b") or just numbers (e.g., "1", "2")
                    question_id_str = str(question_id)

                    # Check if checkbox for this question was marked
                    is_correct = request.POST.get(f'question_{question_id_str}_correct') == 'on'
                    if is_correct:
                        correct_questions.append(question_id_str)

                    # Store question answer
                    QuestionAnswer.objects.update_or_create(
                        submission=submission,
                        question_number=question_id_str,
                        defaults={
                            'is_correct': is_correct,
                            'notes': request.POST.get(f'question_{question_id_str}_notes', ''),
                        }
                    )

                    marks_by_question[question_id_str] = is_correct

                if equal_weight and total_questions > 0:
                    marks_per_question = exam.total_marks / total_questions
                    score = len(correct_questions) * marks_per_question
                else:
                    score = len(correct_questions)

                submission.score = score
                submission.notes = notes
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
                submission.save()

                ExamDistribution.objects.filter(exam=exam, driver=driver).update(status='scored')

                marked_submission, _ = MarkedExamSubmission.objects.get_or_create(submission=submission)
                marked_submission.total_correct = len(correct_questions)
                marked_submission.total_questions = total_questions
                marked_submission.save()

                try:
                    if exam.file and os.path.exists(exam.file.path) and question_mapping:
                        marked_pdf_filename = f"marked_{submission.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                        marked_pdf_dir = os.path.join(str(settings.MEDIA_ROOT), 'marked_submissions')
                        os.makedirs(marked_pdf_dir, exist_ok=True)
                        marked_pdf_path = os.path.join(marked_pdf_dir, marked_pdf_filename)

                        mark_pdf_submission(
                            source_pdf=exam.file.path,
                            output_pdf=marked_pdf_path,
                            driver_name=f"{driver.first_name} {driver.last_name}",
                            exam_title=exam.title,
                            marks=marks_by_question,
                            question_mapping=question_mapping,
                            exam_date=submission.created_at.strftime('%d-%m-%Y')
                        )

                        marked_submission.marked_pdf_file = f"marked_submissions/{marked_pdf_filename}"
                        marked_submission.is_generated = True
                        marked_submission.generation_error = ''
                        marked_submission.save()

                except Exception as e:
                    marked_submission.is_generated = False
                    marked_submission.generation_error = str(e)
                    marked_submission.save()

                AuditHistory.objects.create(
                    action='fast_mark_exam_per_question',
                    entity_type='Submission',
                    entity_id=str(submission.id),
                    user=request.user,
                    details={
                        'exam_id': exam.id,
                        'driver_id': driver.id,
                        'total_questions': total_questions,
                        'correct_questions': len(correct_questions),
                        'score': float(score),
                        'mode': 'per_question',
                        'equal_weight': equal_weight,
                    },
                )

                messages.success(request, f"Exam marked: {len(correct_questions)}/{total_questions} correct. View the marked document below.")
                return redirect('trainapp:view_marked_submission', submission_id=submission.id)

    else:
        form = FastExamMarkingForm()

        existing_answers = QuestionAnswer.objects.filter(submission=submission).values_list('question_number', 'is_correct')
        existing_marks = {qa[0]: qa[1] for qa in existing_answers}

        context = {
            'exam': exam,
            'driver': driver,
            'submission': submission,
            'form': form,
            'detected_questions': detected_questions,
            'question_mapping': question_mapping,
            'existing_marks': existing_marks,
            'detection_error': detection_error,
        }

        return render(request, 'exams/fast_mark_exam.html', context)


@staff_member_required
def exam_results_gallery(request, batch_id=None):
    """
    Advanced exam results viewing platform with batch selection.
    Display all marked exam papers for a selected batch with:
    - Batch filtering
    - PDF viewer with driver info popup
    - Bulk download functionality
    - Print support
    """
    batches = Batch.objects.all().order_by('name')

    # Support both URL path parameter and query parameter for batch selection
    batch_id = batch_id or request.GET.get('batch')

    if batch_id:
        batch = get_object_or_404(Batch, pk=batch_id)
    else:
        batch = batches.first()

    marked_submissions = []

    if batch:
        drivers = batch.drivers.all()
        for driver in drivers:
            submissions = Submission.objects.filter(
                driver=driver
            ).select_related('exam', 'graded_by').prefetch_related('question_answers')

            for submission in submissions:
                marked_sub = MarkedExamSubmission.objects.filter(submission=submission).first()

                if marked_sub and marked_sub.is_generated and marked_sub.marked_pdf_file:
                    question_count = submission.question_answers.count()
                    correct_count = submission.question_answers.filter(is_correct=True).count()

                    marked_submissions.append({
                        'id': submission.id,
                        'driver': driver,
                        'exam': submission.exam,
                        'submission': submission,
                        'marked_submission': marked_sub,
                        'total_questions': marked_sub.total_questions,
                        'total_correct': marked_sub.total_correct,
                        'percentage': marked_sub.get_percentage_score(),
                        'graded_at': submission.graded_at,
                        'can_view': True,
                        'pdf_url': marked_sub.marked_pdf_file.url if marked_sub.marked_pdf_file else '',
                    })

        marked_submissions.sort(key=lambda x: x['graded_at'] or timezone.now(), reverse=True)

    context = {
        'batches': batches,
        'selected_batch': batch,
        'marked_submissions': marked_submissions,
        'total_papers': len(marked_submissions),
        'average_percentage': (sum(m['percentage'] for m in marked_submissions) / len(marked_submissions)) if marked_submissions else 0,
    }

    return render(request, 'exams/exam_results_gallery.html', context)


@staff_member_required
def download_batch_marked_pdfs(request, batch_id):
    """
    Download all marked PDFs for a batch as a ZIP file.
    """
    batch = get_object_or_404(Batch, pk=batch_id)
    drivers = batch.drivers.all()

    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for driver in drivers:
            submissions = Submission.objects.filter(driver=driver).select_related('exam')

            for submission in submissions:
                marked_sub = MarkedExamSubmission.objects.filter(submission=submission).first()

                if marked_sub and marked_sub.is_generated and marked_sub.marked_pdf_file:
                    pdf_file_path = marked_sub.marked_pdf_file.path

                    if os.path.exists(pdf_file_path):
                        # Create organized folder structure: Batch/Exam/Driver_Exam.pdf
                        arcname = f"{batch.name}/{submission.exam.title}/{driver.first_name}_{driver.last_name}_{submission.exam.title}.pdf"
                        zip_file.write(pdf_file_path, arcname=arcname)

    zip_buffer.seek(0)
    response = FileResponse(zip_buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="marked_exams_{batch.name}_{timezone.now().strftime("%Y%m%d")}.zip"'

    return response
