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
    ExamTemplate, QuestionAnswer, MarkedExamSubmission, AuditHistory
)
from .pdf_utils import (
    PDFQuestionDetector, mark_pdf_submission, detect_questions_in_pdf
)


@staff_member_required
@transaction.atomic
def create_exam_template(request, exam_id: int):
    """
    Create or update an ExamTemplate by auto-detecting question positions.
    This is typically called once per exam.
    """
    exam = get_object_or_404(ExamPaper, pk=exam_id)

    if not exam.file:
        messages.error(request, "Exam does not have a file attached. Please upload an exam file first.")
        return redirect('trainingapp:exam_list')

    try:
        file_path = exam.file.path

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Exam file not found at: {file_path}")

        detector = PDFQuestionDetector(file_path)
        detector.open_pdf()
        question_mapping = detector.detect_questions()
        detected_count = detector.get_detected_question_count()
        detector.close_pdf()

        if detected_count == 0:
            messages.warning(
                request,
                "Template created but no questions were detected. Please check the PDF format."
            )

        template, created = ExamTemplate.objects.update_or_create(
            exam=exam,
            defaults={
                'original_file': exam.file,
                'question_mapping': question_mapping,
                'is_processed': True,
                'detected_question_count': detected_count,
            }
        )

        AuditHistory.objects.create(
            action='create_template' if created else 'update_template',
            entity_type='ExamTemplate',
            entity_id=str(template.id),
            user=request.user,
            details={'exam_id': exam.id, 'detected_questions': detected_count},
        )

        if detected_count > 0:
            messages.success(
                request,
                f"Template {'created' if created else 'updated'} successfully. Detected {detected_count} questions."
            )
    except FileNotFoundError as e:
        messages.error(request, f"File error: {str(e)}")
    except Exception as e:
        messages.error(request, f"Error processing template: {str(e)}")

    return redirect('trainingapp:exam_list')


@staff_member_required
def mark_submission_form(request, exam_id: int, driver_id: int):
    """
    Display a form for staff to mark a submission (indicate correct/incorrect per question).
    """
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver = get_object_or_404(Driver, pk=driver_id)

    if not ExamDistribution.objects.filter(exam=exam, driver=driver).exists():
        raise Http404("Driver not assigned to this exam")

    submission = Submission.objects.filter(exam=exam, driver=driver).first()
    if not submission:
        raise Http404("No submission found for this driver-exam pair")

    template = ExamTemplate.objects.filter(exam=exam).first()
    if not template or not template.is_processed:
        messages.warning(request, "Exam template has not been processed yet. Creating template...")
        return redirect('trainingapp:create_exam_template', exam_id=exam.id)

    if request.method == 'POST':
        question_mapping = template.question_mapping
        marks_data = {}
        
        for question_num in range(1, template.detected_question_count + 1):
            is_correct_key = f'question_{question_num}_correct'
            notes_key = f'question_{question_num}_notes'
            
            is_correct = request.POST.get(is_correct_key) == 'on'
            notes = request.POST.get(notes_key, '').strip()
            
            marks_data[question_num] = {
                'is_correct': is_correct,
                'notes': notes,
            }
            
            QuestionAnswer.objects.update_or_create(
                submission=submission,
                question_number=question_num,
                defaults={'is_correct': is_correct, 'notes': notes}
            )
        
        total_correct = sum(1 for m in marks_data.values() if m['is_correct'])
        
        submission.score = Decimal(total_correct)
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()
        
        ExamDistribution.objects.filter(exam=exam, driver=driver).update(status='scored')
        
        generate_marked_pdf(submission, template)
        
        AuditHistory.objects.create(
            action='mark_submission',
            entity_type='Submission',
            entity_id=str(submission.id),
            user=request.user,
            details={
                'exam_id': exam.id,
                'driver_id': driver.id,
                'total_correct': total_correct,
                'total_questions': template.detected_question_count,
            },
        )
        
        messages.success(request, "Submission marked successfully")
        return redirect('trainingapp:submission_list', exam_id=exam.id)

    existing_answers = {
        qa.question_number: qa
        for qa in QuestionAnswer.objects.filter(submission=submission)
    }

    questions = []
    for question_num in range(1, template.detected_question_count + 1):
        existing = existing_answers.get(question_num)
        questions.append({
            'number': question_num,
            'is_correct': existing.is_correct if existing else False,
            'notes': existing.notes if existing else '',
        })

    return render(request, 'exams/mark_submission.html', {
        'exam': exam,
        'driver': driver,
        'submission': submission,
        'questions': questions,
        'template': template,
    })


@staff_member_required
@require_http_methods(["POST"])
def api_mark_question(request):
    """
    API endpoint to mark a single question as correct/incorrect.
    """
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')
        question_number = data.get('question_number')
        is_correct = data.get('is_correct', False)
        notes = data.get('notes', '').strip()
        
        submission = get_object_or_404(Submission, pk=submission_id)
        
        if not request.user.is_staff:
            return JsonResponse(
                {'success': False, 'message': 'Permission denied'},
                status=403
            )
        
        qa, created = QuestionAnswer.objects.update_or_create(
            submission=submission,
            question_number=question_number,
            defaults={'is_correct': is_correct, 'notes': notes}
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Question marked',
            'question_answer_id': qa.id,
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def api_generate_marked_pdf(request):
    """
    API endpoint to generate a marked PDF for a submission.
    """
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')
        
        submission = get_object_or_404(Submission, pk=submission_id)
        template = ExamTemplate.objects.filter(exam=submission.exam).first()
        
        if not template or not template.is_processed:
            return JsonResponse(
                {'success': False, 'message': 'Exam template not processed'},
                status=400
            )
        
        marked_submission = generate_marked_pdf(submission, template)
        
        if not marked_submission or not marked_submission.is_generated:
            error = marked_submission.generation_error if marked_submission else 'Unknown error'
            return JsonResponse(
                {'success': False, 'message': f'Failed to generate PDF: {error}'},
                status=500
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Marked PDF generated',
            'marked_submission_id': marked_submission.id,
            'pdf_url': marked_submission.marked_pdf_file.url if marked_submission.marked_pdf_file else '',
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def generate_marked_pdf(submission: Submission, template: ExamTemplate):
    """
    Generate a marked PDF for a submission based on question answers.
    
    Returns:
        MarkedExamSubmission instance
    """
    marked_submission, created = MarkedExamSubmission.objects.get_or_create(submission=submission)
    
    try:
        if not submission.exam.file:
            raise ValueError("Original exam file not found")
        
        question_answers = QuestionAnswer.objects.filter(submission=submission).values_list(
            'question_number', 'is_correct'
        )
        marks = {int(qa[0]): qa[1] for qa in question_answers}
        
        if not marks:
            raise ValueError("No question marks found for submission")
        
        marked_submission.total_questions = len(marks)
        marked_submission.total_correct = sum(1 for is_correct in marks.values() if is_correct)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_filename = f"marked_{submission.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            output_path = os.path.join(temp_dir, output_filename)
            
            source_pdf = submission.exam.file.path
            
            mark_pdf_submission(
                source_pdf=source_pdf,
                output_pdf=output_path,
                driver_name=str(submission.driver),
                exam_title=submission.exam.title,
                marks=marks,
                question_mapping=template.question_mapping,
                exam_date=submission.graded_at.strftime('%Y-%m-%d') if submission.graded_at else '',
            )
            
            upload_dir = 'marked_submissions'
            os.makedirs(os.path.join(settings.MEDIA_ROOT, upload_dir), exist_ok=True)
            
            final_path = os.path.join(settings.MEDIA_ROOT, upload_dir, output_filename)
            with open(output_path, 'rb') as source:
                with open(final_path, 'wb') as dest:
                    dest.write(source.read())
            
            marked_submission.marked_pdf_file = os.path.join(upload_dir, output_filename)
            marked_submission.is_generated = True
            marked_submission.generation_error = ''
            marked_submission.save()
        
        return marked_submission
    
    except Exception as e:
        marked_submission.is_generated = False
        marked_submission.generation_error = str(e)
        marked_submission.save()
        return marked_submission


@staff_member_required
def view_marked_submission(request, submission_id: int):
    """
    Display a marked submission with the ability to download the marked PDF.
    """
    submission = get_object_or_404(Submission, pk=submission_id)
    
    if not request.user.is_staff:
        raise Http404("Not allowed")
    
    marked_submission = MarkedExamSubmission.objects.filter(submission=submission).first()
    
    question_answers = QuestionAnswer.objects.filter(submission=submission).order_by('question_number')
    
    return render(request, 'exams/view_marked_submission.html', {
        'submission': submission,
        'marked_submission': marked_submission,
        'question_answers': question_answers,
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
    """
    driver = get_object_or_404(Driver, pk=driver_id)

    submissions = Submission.objects.filter(driver=driver).select_related('exam').order_by('-created_at')

    submissions_with_marks = []
    for sub in submissions:
        marked_sub = MarkedExamSubmission.objects.filter(submission=sub).first()
        question_answers = QuestionAnswer.objects.filter(submission=sub)

        submissions_with_marks.append({
            'submission': sub,
            'marked_submission': marked_sub,
            'question_count': question_answers.count(),
            'is_marked': question_answers.count() > 0,
            'can_download': marked_sub and marked_sub.is_generated and marked_sub.marked_pdf_file,
        })

    return render(request, 'exams/driver_submissions.html', {
        'driver': driver,
        'submissions_with_marks': submissions_with_marks,
    })


@staff_member_required
def unified_mark_submission(request, exam_id: int, driver_id: int):
    """
    Advanced unified marking interface with dual document viewer, marking controls, and real-time stats.
    This is a single page that replaces the old mark_submission_form and view_marked_submission.
    """
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver = get_object_or_404(Driver, pk=driver_id)

    if not ExamDistribution.objects.filter(exam=exam, driver=driver).exists():
        raise Http404("Driver not assigned to this exam")

    submission = Submission.objects.filter(exam=exam, driver=driver).first()
    if not submission:
        raise Http404("No submission found for this driver-exam pair")

    template = ExamTemplate.objects.filter(exam=exam).first()
    if not template or not template.is_processed:
        messages.warning(request, "Exam template has not been processed yet. Creating template...")
        return redirect('trainingapp:create_exam_template', exam_id=exam.id)

    if request.method == 'POST':
        question_mapping = template.question_mapping
        marks_data = {}

        for question_num in range(1, template.detected_question_count + 1):
            is_correct_key = f'question_{question_num}_correct'
            notes_key = f'question_{question_num}_notes'

            is_correct = request.POST.get(is_correct_key) == 'on'
            notes = request.POST.get(notes_key, '').strip()

            marks_data[question_num] = {
                'is_correct': is_correct,
                'notes': notes,
            }

            QuestionAnswer.objects.update_or_create(
                submission=submission,
                question_number=question_num,
                defaults={'is_correct': is_correct, 'notes': notes}
            )

        total_correct = sum(1 for m in marks_data.values() if m['is_correct'])

        submission.score = Decimal(total_correct)
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()

        ExamDistribution.objects.filter(exam=exam, driver=driver).update(status='scored')

        generate_marked_pdf(submission, template)

        AuditHistory.objects.create(
            action='mark_submission',
            entity_type='Submission',
            entity_id=str(submission.id),
            user=request.user,
            details={
                'exam_id': exam.id,
                'driver_id': driver.id,
                'total_correct': total_correct,
                'total_questions': template.detected_question_count,
            },
        )

        messages.success(request, "Submission marked successfully and PDF generated")
        return redirect('trainingapp:unified_mark_submission', exam_id=exam.id, driver_id=driver.id)

    existing_answers = {
        qa.question_number: qa
        for qa in QuestionAnswer.objects.filter(submission=submission)
    }

    questions = []
    for question_num in range(1, template.detected_question_count + 1):
        existing = existing_answers.get(question_num)
        questions.append({
            'number': question_num,
            'is_correct': existing.is_correct if existing else False,
            'notes': existing.notes if existing else '',
        })

    marked_submission = MarkedExamSubmission.objects.filter(submission=submission).first()

    total_questions = len(questions)
    total_correct = sum(1 for q in questions if q['is_correct'])
    total_incorrect = total_questions - total_correct
    percentage = round((total_correct / total_questions * 100), 2) if total_questions > 0 else 0

    return render(request, 'exams/unified_mark_submission.html', {
        'exam': exam,
        'driver': driver,
        'submission': submission,
        'questions': questions,
        'template': template,
        'marked_submission': marked_submission,
        'total_questions': total_questions,
        'total_correct': total_correct,
        'total_incorrect': total_incorrect,
        'percentage': percentage,
    })


@staff_member_required
@require_http_methods(["GET"])
def submission_marking_stats(request, exam_id: int):
    """
    Get marking statistics for all submissions of an exam.
    """
    exam = get_object_or_404(ExamPaper, pk=exam_id)

    submissions = Submission.objects.filter(exam=exam).select_related('driver')

    stats = {
        'total_submissions': submissions.count(),
        'marked_submissions': 0,
        'unmarked_submissions': 0,
        'marked_pdfs_generated': 0,
        'submissions': []
    }

    for sub in submissions:
        marked = MarkedExamSubmission.objects.filter(submission=sub).first()
        question_count = QuestionAnswer.objects.filter(submission=sub).count()

        is_marked = question_count > 0

        if is_marked:
            stats['marked_submissions'] += 1
        else:
            stats['unmarked_submissions'] += 1

        if marked and marked.is_generated and marked.marked_pdf_file:
            stats['marked_pdfs_generated'] += 1

        stats['submissions'].append({
            'submission_id': sub.id,
            'driver': str(sub.driver),
            'is_marked': is_marked,
            'question_count': question_count,
            'has_marked_pdf': marked and marked.is_generated,
            'score': float(sub.score) if sub.score else None,
        })

    return JsonResponse(stats)
