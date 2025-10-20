from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BatchForm, DriverForm, ExamUploadForm, ScoreForm, TimetableEntryForm, NotificationForm, NotificationResponseForm
from .models import AuditHistory, Batch, Driver, ExamDistribution, ExamPaper, Submission, TimetableEntry, Notification, NotificationReceipt



@login_required
def dashboard(request):
    if not request.user.is_staff and hasattr(request.user, 'driver_profile') and request.user.driver_profile:
        return redirect('trainingapp:driver_portal')
    drivers_count = Driver.objects.count()
    batch_count = Batch.objects.count()
    exams_count = ExamPaper.objects.count()
    scored_count = Submission.objects.exclude(score__isnull=True).count()
    context = {
        "drivers_count": drivers_count,
        "batch_count": batch_count,
        "exams_count": exams_count,
        "scored_count": scored_count,
    }
    return render(request, "dashboard-02.html", context)



@staff_member_required
def driver_list(request):
    drivers = Driver.objects.select_related("batch").order_by("-created_at")
    return render(request, "drivers/driver_list.html", {"drivers": drivers})



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
            return redirect("trainingapp:driver_list")
    else:
        form = DriverForm(instance=driver)
    return render(request, "drivers/driver_form.html", {"form": form, "title": "Edit Driver"})



@staff_member_required
def batch_list(request):
    batches = Batch.objects.order_by("-created_at")
    return render(request, "batches/batch_list.html", {"batches": batches})



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
    distributions = (
        ExamDistribution.objects.filter(exam=exam)
        .select_related("driver")
        .order_by("driver__first_name", "driver__last_name")
    )
    submissions = {s.driver_id: s for s in Submission.objects.filter(exam=exam)}
    rows = []
    for d in distributions:
        sub = submissions.get(d.driver_id)
        rows.append({
            "driver": d.driver,
            "status": d.status,
            "score": sub.score if sub else None,
        })
    return render(
        request,
        "exams/submission_list.html",
        {"exam": exam, "rows": rows, "distributions": distributions},
    )



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

    return render(request, 'drivers/driver_portal.html', {
        'driver': driver,
        'progress_rows': progress_rows,
        'upcoming': upcoming,
    })
