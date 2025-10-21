# Exam Marking System - Setup and Usage Guide

## Overview

This document explains the new advanced exam marking system implementation that allows staff to:
- Auto-detect question positions in PDF exams
- Mark submissions with correct/incorrect indicators
- Generate marked PDFs with score summaries
- Reuse exam templates for efficiency

## Installation Requirements

### 1. Install PyMuPDF (fitz)

The system requires PyMuPDF for PDF processing. Install it with:

```bash
pip install PyMuPDF
```

### 2. Apply Migrations

After installing PyMuPDF, apply the database migrations:

```bash
python manage.py migrate
```

This creates three new tables:
- `trainapp_examtemplate` - Stores exam templates with question positions
- `trainapp_questionanswer` - Stores individual question marks for submissions
- `trainapp_markedexamsubmission` - Stores generated marked PDFs

## Workflow

### Step 1: Upload Exam

1. Go to **Exams** → **Upload Exam**
2. Upload a PDF or DOCX file
3. Assign to a batch and set total marks

### Step 2: Create Exam Template (One-time)

1. Go to **Exams** list
2. Click **Process Template** button on the exam
3. The system will:
   - Auto-detect question numbers in the PDF
   - Save question positions (page, x, y coordinates)
   - Display detected question count

**Notes:**
- The system detects questions using patterns like: "1.", "2)", "Q3", "(1)", etc.
- This is a one-time operation per exam
- Results are cached and reused for all submissions

### Step 3: Distribute Exam to Drivers

1. Go to **Exams** → Click **Distribute** 
2. The exam is assigned to all drivers in the batch
3. Drivers can view the exam and complete it on paper

### Step 4: Mark Submissions

1. Go to **Exams** → Click **Submissions**
2. For each driver, click **Mark ✓/✗** button
3. On the marking form:
   - Check/uncheck boxes to mark answers correct/incorrect
   - Add optional notes per question
   - The summary panel shows real-time score calculation
   - Use **Mark All Correct** or **Mark All Incorrect** buttons for bulk actions
4. Click **Save Marks & Generate PDF**

The system will:
- Record which questions were correct/incorrect
- Generate a marked PDF with:
  - ✓ next to correct answers (green)
  - ✗ next to incorrect answers (red)
  - Score summary at the top of the first page
  - Driver name, exam title, and percentage score

### Step 5: Review Marked Submissions

1. Go to **Exams** → Click **Submissions**
2. For each driver, use the dropdown menu to view the marked submission
3. The marked PDF viewer shows:
   - The original exam with overlaid marks
   - Score summary box
   - Answer breakdown by question
   - Download button for the marked PDF

## Data Models

### ExamTemplate
```python
- exam: OneToOne relationship to ExamPaper
- original_file: Copy of the exam file
- question_mapping: JSON storing detected questions with coordinates
- is_processed: Boolean indicating if questions were detected
- detected_question_count: Number of questions found
```

### QuestionAnswer
```python
- submission: Foreign key to Submission
- question_number: Which question (1, 2, 3, etc.)
- is_correct: Boolean marking if correct
- notes: Optional notes about the answer
```

### MarkedExamSubmission
```python
- submission: OneToOne relationship to Submission
- marked_pdf_file: Path to generated marked PDF
- total_correct: Count of correct answers
- total_questions: Total questions in exam
- is_generated: Whether PDF was successfully generated
- generation_error: Error message if generation failed
```

## API Endpoints

### Mark a Single Question
```
POST /api/mark-question/
Body: {
    "submission_id": 123,
    "question_number": 1,
    "is_correct": true,
    "notes": "Optional notes"
}
```

### Generate Marked PDF
```
POST /api/generate-marked-pdf/
Body: {
    "submission_id": 123
}
```

### Get Marking Statistics
```
GET /api/marking-stats/{exam_id}/
Returns: {
    "total_submissions": 10,
    "marked_submissions": 7,
    "unmarked_submissions": 3,
    "marked_pdfs_generated": 6,
    "submissions": [...]
}
```

## Admin Interface

New admin pages for:
- **Exam Templates**: View/manage question position data
- **Question Answers**: Review all marked answers
- **Marked Exam Submissions**: Monitor PDF generation status

## Features

### Auto-Detection Patterns
The system recognizes these question number formats:
- "1. Question text..." 
- "2) Question text..."
- "Q3. Question text..."
- "(1) Question text..."

### Question Position Mapping
Detected questions are stored as:
```json
{
    "1": {
        "page": 0,
        "x": 50.5,
        "y": 100.2,
        "text": "1. What is..."
    },
    "2": {
        "page": 0,
        "x": 50.5,
        "y": 150.2,
        "text": "2. Which one..."
    }
}
```

### PDF Generation
Generated marked PDFs include:
- Original exam document
- Question marks (✓/✗) overlaid at detected positions
- Color-coded marks (green for correct, red for incorrect)
- Score summary box with:
  - Driver name
  - Exam title
  - Score (e.g., 7/10)
  - Percentage
  - Date marked

## Troubleshooting

### Issue: "PyMuPDF (fitz) is required"
**Solution**: Install PyMuPDF:
```bash
pip install PyMuPDF
```

### Issue: No questions detected
**Possible causes:**
1. PDF uses unusual question numbering format
2. Question numbers are in images (not extractable text)
3. PDF is scanned without OCR

**Solution:**
- Try uploading a different format or OCR-processed PDF
- Manually check if question patterns match the system's patterns

### Issue: Marks not appearing on PDF
**Check:**
1. Ensure exam template was processed successfully
2. Verify question count in template matches actual questions
3. Check PDF generation didn't have errors in admin panel

### Issue: PDF file not found after generation
**Possible causes:**
1. File system permissions issue
2. MEDIA_ROOT not properly configured
3. Disk space full

**Solution:**
- Check Django settings.MEDIA_ROOT is writable
- Ensure sufficient disk space
- Check server logs for detailed error messages

## Configuration (settings.py)

Ensure your Django settings include:

```python
# Media files configuration
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Database migrations location
MIGRATION_MODULES = {
    'trainapp': 'trainapp.migrations',
}
```

## Advanced Features for Future

1. **Batch Marking**: Mark multiple submissions at once
2. **Question Analytics**: View which questions drivers struggle with
3. **Template Variations**: Support multiple versions of same exam
4. **Custom Mark Symbols**: Allow custom checkmarks/crosses
5. **Automatic Scoring**: Option to auto-score if question key is provided
6. **Export Reports**: Generate marking reports in Excel/PDF

## Database Backup

Before processing templates or marking submissions, backup your database:

```bash
python manage.py dumpdata > backup_before_marking.json
```

To restore:

```bash
python manage.py loaddata backup_before_marking.json
```

## Performance Considerations

- Question detection can take 2-10 seconds per PDF depending on size
- PDF generation is cached - no need to regenerate for same submission
- Store original exam files in efficient storage (not inline)
- For large exams (100+ questions), consider pagination in UI

## Security Notes

- Only staff members can create templates and mark submissions
- Marked PDFs are stored in MEDIA_ROOT with access control
- All marking actions are logged in AuditHistory
- Question answers are validated before saving

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Django and PyMuPDF documentation
3. Check application logs for detailed error messages
