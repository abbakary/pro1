# Quick Start Guide - Advanced Exam Marking System

## 🚀 Getting Started in 5 Minutes

### Prerequisites
- Python 3.8+
- Django 5.2.7
- Existing Django training application running

---

## Installation Steps

### Step 1: Install PyMuPDF
```bash
# In your project root directory
pip install PyMuPDF
```

If you're using requirements.txt (provided):
```bash
pip install -r training/requirements.txt
```

### Step 2: Apply Migrations
```bash
cd training
python manage.py migrate
```

This creates 3 new database tables:
- `trainapp_examtemplate` - Question position data
- `trainapp_questionanswer` - Question marking records
- `trainapp_markedexamsubmission` - Generated marked PDFs

### Step 3: Restart Dev Server
The application will automatically reload.

---

## Using the Exam Marking System

### Workflow Overview

```
1. Upload Exam → 2. Create Template → 3. Distribute → 4. Mark → 5. Review
```

### Step-by-Step Usage

#### 1️⃣ Upload an Exam (If not already done)
- Navigate to **Exams** → **Upload Exam**
- Select a PDF file with clear question numbers (1., 2., 3., etc.)
- Assign to a batch
- Click Upload

#### 2️⃣ Create Exam Template (One-time per exam)
- Go to **Exams** list
- Find your exam in the table
- Click **"Process Template"** button
- Wait for the system to detect questions (2-10 seconds)
- You'll see a success message with the detected question count

**What happens:**
- System reads the PDF and finds all question numbers
- Saves coordinates of each question (page, x, y position)
- This template is reused for all drivers taking this exam

#### 3️⃣ Distribute Exam to Drivers
- In **Exams** list, click **"Distribute"** button
- Exam is assigned to all drivers in that batch
- Drivers can now see the exam in their portal

#### 4️⃣ Mark Submissions
- Go to **Exams** → Click **"Submissions"** for your exam
- For each driver, click the **"Mark ✓/��"** button

**In the marking form:**
- For each question: Check the checkbox if correct, leave unchecked if incorrect
- Optional: Add notes for each question
- The **Summary Panel** on the right shows:
  - Total questions
  - Correct answers count
  - Incorrect answers count
  - Score percentage (real-time)

**Quick Actions:**
- **"Mark All Correct ✓"** - Quickly mark all as correct, then adjust
- **"Mark All Incorrect ✗"** - Quickly mark all as incorrect, then adjust

- Click **"Save Marks & Generate PDF"** button
- System automatically:
  - Records all marks
  - Generates a marked PDF
  - Overlays ✓ (green) for correct answers
  - Overlays ✗ (red) for incorrect answers
  - Adds score summary on the first page

#### 5️⃣ Review Marked Submissions
- Back in **Submissions** list
- Click the driver's name or a "View" button
- You'll see:
  - Original exam PDF with overlaid marks
  - Score box showing X/Y (e.g., 7/10)
  - Percentage score
  - Breakdown of each question
  - **"Download Marked PDF"** button to get a copy

---

## What Gets Generated

### Marked PDF Contents
```
┌─────────────────────────────────────────┐
│        EXAM MARKING SUMMARY             │
│                                         │
│  Driver: John Doe                       │
│  Exam: Road Safety Test                 │
│  Score: 8/10 (80%)                      │
│  Date: 2025-01-15                       │
└─────────────────────────────────────────┘

[Original exam PDF with overlaid marks]

Question 1: ✓ (correct - green)
Question 2: ✗ (incorrect - red)
...
```

---

## Example Scenario

**Your Exam:** Road Safety Test (10 questions, PDF format)

**Process:**
1. Upload the PDF to the system
2. Click "Process Template" → System detects all 10 questions
3. Distribute to Batch A (25 drivers)
4. As drivers submit:
   - Click "Mark ✓/✗" for John Doe
   - Check boxes: Q1✓, Q2✗, Q3✓, Q4✓, Q5✗, Q6✓, Q7✓, Q8✗, Q9✓, Q10✓
   - System shows: 8 correct, 2 incorrect, 80% score
   - Click "Save & Generate PDF"
5. John Doe's marked PDF is ready:
   - Shows original PDF with marks
   - Summary: "John Doe - Road Safety Test - Score: 8/10 (80%)"

**For Audit:**
- Managers can view the marked PDF
- Download it for records
- See exactly which questions were correct/incorrect
- No manual cross-checking needed!

---

## Admin Features

### View Marking Data in Admin Panel
1. Go to Django Admin `/admin/`
2. Look for new sections:
   - **Exam Templates** - See detected questions
   - **Question Answers** - Review all marks
   - **Marked Exam Submissions** - Track PDF generation

---

## Common Actions

### Mark All Correct
```
1. Click "Mark ✓/✗"
2. Click "Mark All Correct ✓" button
3. Adjust any that should be wrong
4. Click "Save Marks & Generate PDF"
```

### Mark All Incorrect
```
1. Click "Mark ✓/✗"
2. Click "Mark All Incorrect ✗" button
3. Adjust any that should be correct
4. Click "Save Marks & Generate PDF"
```

### View Already Marked Submission
```
1. Go to Submissions
2. Click driver's name or "View Marked" link
3. See PDF with marks and score
4. Download if needed
```

### Edit Previous Markings
```
1. Click "Mark ✓/✗" again
2. Change any marks as needed
3. Save to regenerate PDF with new marks
```

---

## Keyboard Shortcuts (In Marking Form)

- **Tab** - Move between questions
- **Space** - Toggle current question's correct/incorrect
- **Enter** - Submit form (same as clicking Save button)

---

## Troubleshooting

### "No questions detected"
- Check if PDF is a real PDF (not image-based)
- Ensure questions start with numbers: 1., 2), Q3, etc.
- Try uploading a different PDF to test

### "PyMuPDF not installed"
- Run: `pip install PyMuPDF`
- Restart your dev server

### "Marked PDF not showing"
- Check that template was processed (should show "Processed" badge)
- Ensure all questions were marked
- Check server logs for errors

---

## File Storage

**Marked PDFs are stored in:**
```
training/media/marked_submissions/marked_[id]_[timestamp].pdf
```

**Important:** Keep this directory backed up if needed for compliance/audit.

---

## Performance Tips

1. **Process templates once** - Don't reprocess the same exam
2. **Batch marking** - Mark multiple drivers in succession
3. **Large exams** - For 100+ question exams, mark 10-20 at a time
4. **Disk space** - Each PDF takes 200KB-5MB, plan accordingly

---

## What Happens Behind the Scenes

When you click "Save Marks & Generate PDF":

```
1. System reads your check/uncheck marks
2. Finds the exam template with question positions
3. Opens the original PDF
4. For each question:
   - Locates the position (page, x, y)
   - Overlays ✓ if correct (green) or ✗ if incorrect (red)
5. Adds score summary box on first page
6. Saves the marked PDF
7. Updates the database with generation status
```

**Total time:** Usually 2-10 seconds per exam

---

## Security

✅ **Only staff can:**
- Process templates
- Mark submissions
- Generate marked PDFs
- Download marked PDFs

✅ **All actions are logged:**
- Who marked what
- When it was marked
- Changes made
- View in AuditHistory

---

## Frequently Asked Questions

**Q: Can I edit marks after generating a PDF?**
A: Yes! Click "Mark ✓/✗" again, adjust marks, and save. It regenerates the PDF.

**Q: What if the exam has more than 100 questions?**
A: System supports up to 1000 questions. Form might be long, but fully functional.

**Q: Can drivers see the marked PDFs?**
A: Currently only staff can view. This can be customized per your needs.

**Q: What if PDF generation fails?**
A: Error message shows in the submission view. Check server logs for details.

**Q: Can I use Word documents instead of PDF?**
A: System works best with PDFs. Word docs need to be converted to PDF first.

**Q: How do I backup my marked PDFs?**
A: Back up the `training/media/marked_submissions/` folder.

---

## Next Steps

1. ✅ Install PyMuPDF: `pip install PyMuPDF`
2. ✅ Run migrations: `python manage.py migrate`
3. ✅ Upload a test exam
4. ✅ Create a template
5. ✅ Try marking a submission
6. ✅ Review the marked PDF

---

## Support Resources

1. **Full Setup Guide:** `EXAM_MARKING_SETUP.md`
2. **Implementation Details:** `IMPLEMENTATION_SUMMARY.md`
3. **Django Admin:** Built-in admin interface for data review
4. **Server Logs:** Check for error details if issues occur

---

**You're all set! Happy marking! 🎯**
