from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction, models
from django.db.models import Q, Count, Avg
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import json

from .forms import BatchForm, DriverForm, ExamUploadForm, ScoreForm, TimetableEntryForm, NotificationForm, NotificationResponseForm
from .models import AuditHistory, Batch, Driver, ExamDistribution, ExamPaper, Submission, TimetableEntry, Notification, NotificationReceipt



@login_required
def dashboard(request):
    if not request.user.is_staff and hasattr(request.user, 'driver_profile') and request.user.driver_profile:
        return redirect('trainingapp:driver_portal')

    now = timezone.now()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_week = now - timezone.timedelta(days=7)
    last_month = now - timezone.timedelta(days=30)

    drivers_count = Driver.objects.count()
    batch_count = Batch.objects.count()
    exams_count = ExamPaper.objects.count()
    submissions_total = Submission.objects.count()
    scored_count = Submission.objects.exclude(score__isnull=True).count()
    pending_score = Submission.objects.filter(score__isnull=True).count()

    new_drivers_this_month = Driver.objects.filter(created_at__gte=first_of_month).count()
    new_drivers_this_week = Driver.objects.filter(created_at__gte=last_week).count()

    new_submissions_this_week = Submission.objects.filter(created_at__gte=last_week).count()
    new_submissions_this_month = Submission.objects.filter(created_at__gte=first_of_month).count()

    status_counts_qs = ExamDistribution.objects.values('status').annotate(c=Count('id'))
    status_counts = {row['status']: row['c'] for row in status_counts_qs}
    status_counts = {
        'assigned': status_counts.get('assigned', 0),
        'completed': status_counts.get('completed', 0),
        'scored': status_counts.get('scored', 0),
    }

    top_batches = (
        Batch.objects.annotate(exams_count=Count('exams'), drivers_count=Count('drivers'))
        .order_by('-exams_count', 'name')[:8]
    )
    batch_labels = [b.name for b in top_batches]
    batch_exam_counts = [b.exams_count for b in top_batches]
    batch_driver_counts = [b.drivers_count for b in top_batches]

    upcoming_total = TimetableEntry.objects.filter(starts_at__gte=now).count()
    recent_exams = ExamPaper.objects.select_related('batch').order_by('-created_at')[:8]

    recent_submissions = (
        Submission.objects.select_related('driver', 'exam')
        .order_by('-created_at')[:10]
    )

    pending_submissions = (
        Submission.objects.filter(score__isnull=True)
        .select_related('driver', 'exam')
        .order_by('created_at')[:10]
    )

    top_performing_drivers = (
        Driver.objects
        .annotate(avg_score=models.Avg('submissions__score'), score_count=Count('submissions__score', filter=models.Q(submissions__score__isnull=False)))
        .filter(score_count__gt=0)
        .order_by('-avg_score')[:5]
    )

    context = {
        'drivers_count': drivers_count,
        'batch_count': batch_count,
        'exams_count': exams_count,
        'submissions_total': submissions_total,
        'scored_count': scored_count,
        'pending_score': pending_score,
        'new_drivers_this_month': new_drivers_this_month,
        'new_drivers_this_week': new_drivers_this_week,
        'new_submissions_this_week': new_submissions_this_week,
        'new_submissions_this_month': new_submissions_this_month,
        'status_counts': status_counts,
        'batch_labels': batch_labels,
        'batch_exam_counts': batch_exam_counts,
        'batch_driver_counts': batch_driver_counts,
        'upcoming_total': upcoming_total,
        'recent_exams': recent_exams,
        'recent_submissions': recent_submissions,
        'pending_submissions': pending_submissions,
        'top_performing_drivers': top_performing_drivers,
        'now_time': now,
    }
    return render(request, 'dashboard-02.html', context)



@staff_member_required
def driver_list(request):
    q = request.GET.get('q', '').strip()
    batch = request.GET.get('batch', '').strip()
    status_filter = request.GET.get('status', '').strip()

    drivers = Driver.objects.select_related("batch").order_by("-created_at")

    if q:
        drivers = drivers.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(license_no__icontains=q)
        )

    if batch:
        drivers = drivers.filter(batch_id=batch)

    if status_filter == 'with_contact':
        drivers = drivers.filter(Q(phone__isnull=False, phone__gt=''))
    elif status_filter == 'no_contact':
        drivers = drivers.filter(Q(phone__isnull=True) | Q(phone=''))

    batches = Batch.objects.all().order_by('name')
    return render(request, "drivers/driver_list.html", {"drivers": drivers, "batches": batches})



@staff_member_required
def driver_create(request):
    if request.method == "POST":
        form = DriverForm(request.POST, request.FILES)
        if form.is_valid():
            driver = form.save()
            AuditHistory.objects.create(
                action="create",
                entity_type="Driver",
                entity_id=str(driver.id),
                user=request.user,
                details={"first_name": driver.first_name},
            )
            messages.success(request, "Driver created successfully")
            return redirect("trainingapp:driver_list")
    else:
        form = DriverForm()
    return render(request, "drivers/driver_form.html", {"form": form, "title": "Add Driver"})



@staff_member_required
def driver_detail(request, pk: int):
    """
    Display comprehensive driver information including profile, contact details,
    exam history, scores, and submission status.
    """
    driver = get_object_or_404(Driver, pk=pk)

    distributions = ExamDistribution.objects.filter(driver=driver).select_related('exam').order_by('-created_at')
    submissions = Submission.objects.filter(driver=driver).select_related('exam').order_by('-created_at')

    submissions_with_details = []
    for sub in submissions:
        marked_sub = sub.marked_version if hasattr(sub, 'marked_version') else None
        question_count = sub.question_answers.count()

        submissions_with_details.append({
            'submission': sub,
            'exam': sub.exam,
            'marked_submission': marked_sub,
            'question_count': question_count,
            'is_marked': question_count > 0,
            'score_percentage': round((float(sub.score) / sub.exam.total_marks * 100), 2) if sub.score else None,
            'status': 'Scored' if sub.score else 'Pending',
        })

    statistics = {
        'total_exams': distributions.count(),
        'completed_exams': submissions.count(),
        'scored_exams': submissions.exclude(score__isnull=True).count(),
        'pending_exams': submissions.filter(score__isnull=True).count(),
        'average_score': submissions.exclude(score__isnull=True).aggregate(avg=Avg('score'))['avg'] or 0,
    }

    if statistics['scored_exams'] > 0:
        statistics['average_percentage'] = round(
            (statistics['average_score'] / 100 * 100), 2
        )
    else:
        statistics['average_percentage'] = 0

    context = {
        'driver': driver,
        'distributions': distributions,
        'submissions_with_details': submissions_with_details,
        'statistics': statistics,
    }

    return render(request, 'drivers/driver_detail.html', context)


@staff_member_required
def driver_edit(request, pk: int):
    driver = get_object_or_404(Driver, pk=pk)
    if request.method == "POST":
        form = DriverForm(request.POST, instance=driver)
        if form.is_valid():
            driver = form.save()
            AuditHistory.objects.create(
                action="update",
                entity_type="Driver",
                entity_id=str(driver.id),
                user=request.user,
                details={"first_name": driver.first_name},
            )
            messages.success(request, "Driver updated successfully")
            return redirect("trainingapp:driver_detail", pk=driver.id)
    else:
        form = DriverForm(instance=driver)
    return render(request, "drivers/driver_form.html", {"form": form, "title": "Edit Driver"})



@staff_member_required
def batch_list(request):
    batches = Batch.objects.order_by("-created_at")
    return render(request, "batches/batch_list.html", {"batches": batches})



@staff_member_required
def timetable_list(request):
    entries = (
        TimetableEntry.objects.select_related('batch', 'driver')
        .order_by('-starts_at')
    )
    return render(request, 'timetable/timetable_list.html', {"entries": entries})


@staff_member_required
def timetable_create(request):
    if request.method == 'POST':
        form = TimetableEntryForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.created_by = request.user
            t.save()
            AuditHistory.objects.create(
                action="create_timetable",
                entity_type="TimetableEntry",
                entity_id=str(t.id),
                user=request.user,
                details={"title": t.title},
            )
            messages.success(request, "Timetable entry created")
            return redirect('trainingapp:timetable_list')
    else:
        form = TimetableEntryForm()
    return render(request, 'timetable/timetable_form.html', {"form": form, "title": "Add Timetable Entry"})


@staff_member_required
def notification_list(request):
    items = Notification.objects.order_by('-created_at')
    return render(request, 'notifications/notification_list.html', {"items": items})


@staff_member_required
def notification_create(request):
    if request.method == 'POST':
        form = NotificationForm(request.POST, request.FILES)
        if form.is_valid():
            notif = form.save(commit=False)
            notif.created_by = request.user
            notif.save()
            created = 0
            if notif.driver:
                NotificationReceipt.objects.get_or_create(notification=notif, driver=notif.driver)
                created = 1
            elif notif.batch:
                for d in Driver.objects.filter(batch=notif.batch):
                    NotificationReceipt.objects.get_or_create(notification=notif, driver=d)
                    created += 1
            AuditHistory.objects.create(
                action="create_notification",
                entity_type="Notification",
                entity_id=str(notif.id),
                user=request.user,
                details={"title": notif.title, "recipients": created},
            )
            messages.success(request, f"Notification sent to {created} driver(s)")
            return redirect('trainingapp:notification_list')
    else:
        form = NotificationForm()
    return render(request, 'notifications/notification_form.html', {"form": form, "title": "Send Notification"})


@staff_member_required
def notification_detail(request, pk: int):
    notif = get_object_or_404(Notification, pk=pk)
    receipts = (
        NotificationReceipt.objects.filter(notification=notif)
        .select_related('driver')
        .order_by('-created_at')
    )
    return render(request, 'notifications/notification_detail.html', {"notification": notif, "receipts": receipts})


@login_required
def notification_respond(request, receipt_id: int):
    driver = getattr(request.user, 'driver_profile', None)
    receipt = get_object_or_404(NotificationReceipt, pk=receipt_id)
    if driver is None or receipt.driver_id != driver.id:
        raise Http404("Not allowed")
    if request.method == 'POST':
        form = NotificationResponseForm(request.POST)
        if form.is_valid():
            resp = form.save(commit=False)
            resp.receipt = receipt
            resp.save()
            messages.success(request, "Response sent")
            return redirect('trainingapp:driver_portal')
    return redirect('trainingapp:driver_portal')


@staff_member_required
def batch_create(request):
    if request.method == "POST":
        form = BatchForm(request.POST)
        if form.is_valid():
            batch = form.save()
            AuditHistory.objects.create(
                action="create",
                entity_type="Batch",
                entity_id=str(batch.id),
                user=request.user,
                details={"name": batch.name},
            )
            messages.success(request, "Batch created successfully")
            return redirect("trainingapp:batch_list")
    else:
        form = BatchForm()
    return render(request, "batches/batch_form.html", {"form": form, "title": "Add Batch"})



@staff_member_required
def exam_list(request):
    exams = ExamPaper.objects.select_related("batch").order_by("-created_at")
    return render(request, "exams/exam_list.html", {"exams": exams})



@staff_member_required
def exam_upload(request):
    if request.method == "POST":
        form = ExamUploadForm(request.POST, request.FILES)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.created_by = request.user
            exam.save()
            AuditHistory.objects.create(
                action="upload_exam",
                entity_type="ExamPaper",
                entity_id=str(exam.id),
                user=request.user,
                details={"title": exam.title},
            )
            messages.success(request, "Exam paper uploaded")
            return redirect("trainingapp:exam_list")
    else:
        form = ExamUploadForm()
    return render(request, "exams/exam_upload.html", {"form": form})



@staff_member_required
@transaction.atomic
def exam_distribute(request, pk: int):
    exam = get_object_or_404(ExamPaper, pk=pk)
    if exam.batch is None:
        raise Http404("Exam is not linked to a batch")

    batch_drivers = Driver.objects.filter(batch=exam.batch)
    created = 0
    for d in batch_drivers:
        _, was_created = ExamDistribution.objects.get_or_create(exam=exam, driver=d)
        if was_created:
            created += 1
    messages.success(request, f"Distributed to {created} drivers in batch {exam.batch.name}")
    AuditHistory.objects.create(
        action="distribute_exam",
        entity_type="ExamPaper",
        entity_id=str(exam.id),
        user=request.user,
        details={"batch": exam.batch.name, "created": created},
    )
    return redirect("trainingapp:submission_list", exam_id=exam.id)



@staff_member_required
def submission_list(request, exam_id: int):
    exam = get_object_or_404(ExamPaper, pk=exam_id)

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    min_score = request.GET.get('min_score', '').strip()
    max_score = request.GET.get('max_score', '').strip()

    base_qs = ExamDistribution.objects.filter(exam=exam).select_related('driver')
    if q:
        base_qs = base_qs.filter(Q(driver__first_name__icontains=q) | Q(driver__last_name__icontains=q) | Q(driver__license_no__icontains=q))
    if status:
        base_qs = base_qs.filter(status=status)

    score_filtered = False
    if min_score or max_score:
        score_filtered = True
        if min_score:
            base_qs = base_qs.filter(driver__submissions__exam=exam, driver__submissions__score__gte=min_score)
        if max_score:
            base_qs = base_qs.filter(driver__submissions__exam=exam, driver__submissions__score__lte=max_score)

    distributions = base_qs.order_by('driver__first_name', 'driver__last_name')

    submissions_map = {s.driver_id: s for s in Submission.objects.filter(exam=exam)}
    rows = []
    for d in distributions:
        sub = submissions_map.get(d.driver_id)
        if score_filtered and sub is None:
            continue
        rows.append({
            'driver': d.driver,
            'status': d.status,
            'score': sub.score if sub else None,
        })

    ctx = {
        'exam': exam,
        'rows': rows,
        'q': q,
        'status': status,
        'min_score': min_score,
        'max_score': max_score,
    }
    return render(request, 'exams/submission_list.html', ctx)


@staff_member_required
def exam_results_print(request, exam_id: int):
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver_id = request.GET.get('driver_id')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    min_score = request.GET.get('min_score', '').strip()
    max_score = request.GET.get('max_score', '').strip()

    base_qs = ExamDistribution.objects.filter(exam=exam).select_related('driver')
    if driver_id:
        base_qs = base_qs.filter(driver_id=driver_id)
    if q:
        base_qs = base_qs.filter(Q(driver__first_name__icontains=q) | Q(driver__last_name__icontains=q) | Q(driver__license_no__icontains=q))
    if status:
        base_qs = base_qs.filter(status=status)

    score_filtered = False
    if min_score or max_score:
        score_filtered = True
        if min_score:
            base_qs = base_qs.filter(driver__submissions__exam=exam, driver__submissions__score__gte=min_score)
        if max_score:
            base_qs = base_qs.filter(driver__submissions__exam=exam, driver__submissions__score__lte=max_score)

    distributions = base_qs.order_by('driver__first_name', 'driver__last_name')

    submissions_map = {s.driver_id: s for s in Submission.objects.filter(exam=exam)}
    rows = []
    for d in distributions:
        sub = submissions_map.get(d.driver_id)
        if score_filtered and sub is None:
            continue
        rows.append({
            'driver': d.driver,
            'status': d.status,
            'score': sub.score if sub else None,
        })

    return render(request, 'exams/results_print.html', {
        'exam': exam,
        'rows': rows,
        'single_driver': Driver.objects.filter(pk=driver_id).first() if driver_id else None,
    })



@staff_member_required
def score_submission(request, exam_id: int, driver_id: int):
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver = get_object_or_404(Driver, pk=driver_id)
    if not ExamDistribution.objects.filter(exam=exam, driver=driver).exists():
        messages.error(request, "Driver is not assigned this exam")
        return redirect("trainingapp:submission_list", exam_id=exam.id)

    submission, _ = Submission.objects.get_or_create(exam=exam, driver=driver)

    if request.method == "POST":
        form = ScoreForm(request.POST, request.FILES, instance=submission)
        if form.is_valid():
            submission = form.save(commit=False)
            if submission.score is not None:
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
            submission.save()
            ExamDistribution.objects.filter(exam=exam, driver=driver).update(status="scored" if submission.score is not None else "completed")
            AuditHistory.objects.create(
                action="score_submission",
                entity_type="Submission",
                entity_id=str(submission.id),
                user=request.user,
                details={"score": float(submission.score) if submission.score is not None else None},
            )
            messages.success(request, "Submission saved")
            return redirect("trainingapp:submission_list", exam_id=exam.id)
    else:
        form = ScoreForm(instance=submission)
    return render(
        request,
        "exams/score_form.html",
        {"form": form, "exam": exam, "driver": driver},
    )



@staff_member_required
def exam_view(request, exam_id: int):
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    file_url = exam.file.url if exam.file else ""
    is_pdf = file_url.lower().endswith(".pdf")
    return render(request, "exams/exam_view.html", {"exam": exam, "is_pdf": is_pdf})


@staff_member_required
def printable_paper(request, exam_id: int, driver_id: int):
    exam = get_object_or_404(ExamPaper, pk=exam_id)
    driver = get_object_or_404(Driver, pk=driver_id)
    submission = Submission.objects.filter(exam=exam, driver=driver).first()
    file_url = exam.file.url if exam.file else ""
    is_pdf = file_url.lower().endswith(".pdf")
    return render(
        request,
        "exams/printable_paper.html",
        {
            "exam": exam,
            "driver": driver,
            "submission": submission,
            "is_pdf": is_pdf,
        },
    )


@login_required
def driver_portal(request):
    driver = getattr(request.user, 'driver_profile', None)
    if driver is None:
        raise Http404("Driver profile not found for this account")

    distributions = (
        ExamDistribution.objects.filter(driver=driver)
        .select_related('exam')
        .order_by('-created_at')
    )
    submissions = {s.exam_id: s for s in Submission.objects.filter(driver=driver)}
    progress_rows = []
    for dist in distributions:
        sub = submissions.get(dist.exam_id)
        progress_rows.append({
            'exam': dist.exam,
            'status': dist.status,
            'score': sub.score if sub else None,
        })

    upcoming = (
        TimetableEntry.objects.filter(Q(driver=driver) | Q(batch=driver.batch))
        .order_by('starts_at')[:10]
    )

    receipts = (
        NotificationReceipt.objects.filter(driver=driver)
        .select_related('notification')
        .order_by('-created_at')
    )
    NotificationReceipt.objects.filter(driver=driver, is_read=False).update(is_read=True)

    return render(request, 'drivers/driver_portal.html', {
        'driver': driver,
        'progress_rows': progress_rows,
        'upcoming': upcoming,
        'receipts': receipts,
        'response_form': NotificationResponseForm(),
    })


@staff_member_required
def score_submissions(request):
    exam_id = request.GET.get('exam_id')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    exams = ExamPaper.objects.select_related('batch').order_by('-created_at')

    rows = []
    selected_exam = None

    if exam_id:
        selected_exam = get_object_or_404(ExamPaper, pk=exam_id)

        base_qs = ExamDistribution.objects.filter(exam=selected_exam).select_related('driver')
        if q:
            base_qs = base_qs.filter(Q(driver__first_name__icontains=q) | Q(driver__last_name__icontains=q) | Q(driver__license_no__icontains=q))
        if status:
            base_qs = base_qs.filter(status=status)

        distributions = base_qs.order_by('driver__first_name', 'driver__last_name')
        submissions_map = {s.driver_id: s for s in Submission.objects.filter(exam=selected_exam)}

        for d in distributions:
            sub = submissions_map.get(d.driver_id)
            rows.append({
                'driver_id': d.driver.id,
                'driver_name': f"{d.driver.first_name} {d.driver.last_name}",
                'license_no': d.driver.license_no,
                'company': d.driver.company,
                'batch': d.driver.batch.name if d.driver.batch else '',
                'status': d.status,
                'score': sub.score if sub else None,
                'notes': sub.notes if sub else '',
                'submission_id': sub.id if sub else None,
            })

    ctx = {
        'exams': exams,
        'selected_exam': selected_exam,
        'rows': rows,
        'q': q,
        'status': status,
    }
    return render(request, 'exams/score_submissions.html', ctx)


@staff_member_required
@require_http_methods(["POST"])
def api_save_score(request):
    try:
        data = json.loads(request.body)
        exam_id = data.get('exam_id')
        driver_id = data.get('driver_id')
        score = data.get('score')
        notes = data.get('notes', '')

        exam = get_object_or_404(ExamPaper, pk=exam_id)
        driver = get_object_or_404(Driver, pk=driver_id)

        if not ExamDistribution.objects.filter(exam=exam, driver=driver).exists():
            return JsonResponse({'success': False, 'message': 'Driver not assigned to this exam'}, status=400)

        submission, _ = Submission.objects.get_or_create(exam=exam, driver=driver)

        submission.notes = notes
        if score is not None and score != '':
            try:
                submission.score = float(score)
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'message': 'Invalid score value'}, status=400)

        submission.save()

        ExamDistribution.objects.filter(exam=exam, driver=driver).update(
            status='scored' if submission.score is not None else 'completed'
        )

        AuditHistory.objects.create(
            action='score_submission_inline',
            entity_type='Submission',
            entity_id=str(submission.id),
            user=request.user,
            details={'score': float(submission.score) if submission.score else None},
        )

        return JsonResponse({
            'success': True,
            'message': 'Score saved successfully',
            'submission_id': submission.id,
            'status': 'scored' if submission.score is not None else 'completed'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
