from django.urls import path
from . import views
from .marking_views import (
    create_exam_template, mark_submission_form, api_mark_question,
    api_generate_marked_pdf, view_marked_submission, download_marked_pdf,
    submission_marking_stats, driver_submissions
)

app_name = 'trainingapp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Drivers
    path('drivers/', views.driver_list, name='driver_list'),
    path('drivers/new/', views.driver_create, name='driver_create'),
    path('drivers/<int:pk>/edit/', views.driver_edit, name='driver_edit'),
    path('drivers/<int:driver_id>/submissions/', driver_submissions, name='driver_submissions'),
    path('driver/me/', views.driver_portal, name='driver_portal'),

    # Batches
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/new/', views.batch_create, name='batch_create'),

    # Timetable
    path('timetable/', views.timetable_list, name='timetable_list'),
    path('timetable/new/', views.timetable_create, name='timetable_create'),

    # Notifications
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/new/', views.notification_create, name='notification_create'),
    path('notifications/<int:pk>/', views.notification_detail, name='notification_detail'),
    path('notifications/respond/<int:receipt_id>/', views.notification_respond, name='notification_respond'),

    # Exams
    path('exams/', views.exam_list, name='exam_list'),
    path('exams/upload/', views.exam_upload, name='exam_upload'),
    path('exams/<int:pk>/distribute/', views.exam_distribute, name='exam_distribute'),
    path('exams/<int:exam_id>/view/', views.exam_view, name='exam_view'),

    # Exam Templates & Marking
    path('exams/<int:exam_id>/create-template/', create_exam_template, name='create_exam_template'),
    path('exams/<int:exam_id>/mark/<int:driver_id>/', mark_submission_form, name='mark_submission'),
    path('submissions/<int:submission_id>/view-marked/', view_marked_submission, name='view_marked_submission'),
    path('submissions/<int:submission_id>/download-marked-pdf/', download_marked_pdf, name='download_marked_pdf'),

    # API Endpoints for Marking
    path('api/mark-question/', api_mark_question, name='api_mark_question'),
    path('api/generate-marked-pdf/', api_generate_marked_pdf, name='api_generate_marked_pdf'),
    path('api/marking-stats/<int:exam_id>/', submission_marking_stats, name='api_marking_stats'),

    # Submissions / Scoring
    path('score-submissions/', views.score_submissions, name='score_submissions'),
    path('exams/<int:exam_id>/submissions/', views.submission_list, name='submission_list'),
    path('exams/<int:exam_id>/results/print/', views.exam_results_print, name='exam_results_print'),
    path('exams/<int:exam_id>/score/<int:driver_id>/', views.score_submission, name='score_submission'),
    path('api/score-submission/', views.api_save_score, name='api_save_score'),

    # Printable / Embedded
    path('exams/<int:exam_id>/paper/<int:driver_id>/', views.printable_paper, name='printable_paper'),
]
