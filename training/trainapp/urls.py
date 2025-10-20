from django.urls import path
from . import views

app_name = 'trainingapp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Drivers
    path('drivers/', views.driver_list, name='driver_list'),
    path('drivers/new/', views.driver_create, name='driver_create'),
    path('drivers/<int:pk>/edit/', views.driver_edit, name='driver_edit'),
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

    # Submissions / Scoring
    path('exams/<int:exam_id>/submissions/', views.submission_list, name='submission_list'),
    path('exams/<int:exam_id>/score/<int:driver_id>/', views.score_submission, name='score_submission'),

    # Printable / Embedded
    path('exams/<int:exam_id>/paper/<int:driver_id>/', views.printable_paper, name='printable_paper'),
]
