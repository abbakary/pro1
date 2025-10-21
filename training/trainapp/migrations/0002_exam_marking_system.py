from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.timezone import now


class Migration(migrations.Migration):

    dependencies = [
        ('trainapp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExamTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('original_file', models.FileField(upload_to='exam_templates/')),
                ('question_mapping', models.JSONField(blank=True, default=dict, help_text='Stores question positions detected from PDF')),
                ('is_processed', models.BooleanField(default=False, help_text='Whether question detection has been completed')),
                ('detected_question_count', models.PositiveIntegerField(default=0)),
                ('exam', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='template', to='trainapp.exampaper')),
            ],
            options={
                'verbose_name': 'Exam Template',
                'verbose_name_plural': 'Exam Templates',
            },
        ),
        migrations.CreateModel(
            name='QuestionAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('question_number', models.PositiveIntegerField()),
                ('is_correct', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True)),
                ('submission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='question_answers', to='trainapp.submission')),
            ],
            options={
                'ordering': ['question_number'],
                'unique_together': {('submission', 'question_number')},
            },
        ),
        migrations.CreateModel(
            name='MarkedExamSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('marked_pdf_file', models.FileField(blank=True, upload_to='marked_submissions/')),
                ('total_correct', models.PositiveIntegerField(default=0)),
                ('total_questions', models.PositiveIntegerField(default=0)),
                ('is_generated', models.BooleanField(default=False)),
                ('generation_error', models.TextField(blank=True)),
                ('submission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='marked_version', to='trainapp.submission')),
            ],
            options={
                'verbose_name': 'Marked Exam Submission',
                'verbose_name_plural': 'Marked Exam Submissions',
            },
        ),
    ]
