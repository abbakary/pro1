import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from django.utils import timezone

try:
    import fitz
except ImportError:
    fitz = None


class PDFQuestionDetector:
    """Detects question positions in PDF files using text extraction and regex patterns.

    Supports multiple question formats:
    - Simple: 1., 2., 3., ... or 1), 2), 3), ...
    - With sub-parts: 1(a), 1(b), 2(a), 2(b), ... or 1a), 1b), 2a), ...
    - Q format: Q1, Q2, Q3, ...
    - Question word: Question 1, Question 2, ...
    - Parenthetical: (1), (2), (3), ...
    """

    # Patterns with capture groups for main question and optional sub-part
    QUESTION_PATTERNS = [
        # Format: 1(a), 1(b), 2(a), etc. - main question in group 1, sub-part in group 2
        (r'^\s*(\d+)\s*\(\s*([a-zA-Z])\s*\)\s*[\.\):\-]?\s*', 'subpart'),
        # Format: 1a), 1b), 2a), etc. - main question in group 1, sub-part in group 2
        (r'^\s*(\d+)\s*([a-zA-Z])\s*[\)\.\:\-]\s*', 'subpart'),
        # Format: 1., 1), 1-, 1: (simple numbered, most common)
        (r'^\s*(\d+)\s*[\.\):\-]\s*', 'simple'),
        # Format: Q1, Q2, Q3
        (r'^\s*Q\s*(\d+)\s*[\.\):\-]?\s*', 'simple'),
        # Format: Question 1, Question 2
        (r'^\s*Question\s+(\d+)\s*[\.\):\-]?\s*', 'simple'),
        # Format: (1), (2), (3)
        (r'^\s*\(\s*(\d+)\s*\)\s*', 'simple'),
    ]

    def __init__(self, pdf_path: str):
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is required for PDF processing. Install it with: pip install PyMuPDF")

        self.pdf_path = pdf_path
        self.doc = None
        self.question_mapping = {}
        self.detected_questions = []
        
    def open_pdf(self) -> bool:
        """Open the PDF file and validate it."""
        try:
            self.doc = fitz.open(self.pdf_path)
            return True
        except Exception as e:
            raise ValueError(f"Failed to open PDF: {str(e)}")
    
    def close_pdf(self):
        """Close the PDF document."""
        if self.doc:
            self.doc.close()
            self.doc = None
    
    def extract_text_with_coordinates(self) -> List[Dict[str, Any]]:
        """Extract text with position coordinates from the PDF."""
        if not self.doc:
            self.open_pdf()
        
        text_blocks = []
        
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text_dict = page.get_text("dict")
            
            for block in text_dict.get("blocks", []):
                if block["type"] == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                bbox = span.get("bbox", (0, 0, 0, 0))
                                text_blocks.append({
                                    "text": text,
                                    "page": page_num,
                                    "x0": bbox[0],
                                    "y0": bbox[1],
                                    "x1": bbox[2],
                                    "y1": bbox[3],
                                })
        
        return text_blocks
    
    def detect_questions(self) -> Dict[str, Dict[str, Any]]:
        """Detect question numbers and their positions in the PDF.

        Returns a mapping of question identifiers to their positions.
        For simple questions: "1", "2", "3", etc.
        For sub-part questions: "1a", "1b", "2a", "2b", etc.
        """
        text_blocks = self.extract_text_with_coordinates()

        question_mapping = {}
        detected_questions = []

        for block in text_blocks:
            text = block["text"]
            for pattern, question_type in self.QUESTION_PATTERNS:
                match = re.match(pattern, text)
                if match:
                    try:
                        if question_type == 'subpart':
                            # Sub-part question: main_num + sub_letter (e.g., "1a", "1b", "2a")
                            main_num = int(match.group(1))
                            sub_letter = match.group(2).lower()
                            question_id = f"{main_num}{sub_letter}"
                        else:
                            # Simple question: just the number
                            question_id = match.group(1)

                        # Only add if not already detected (first occurrence wins)
                        if question_id not in question_mapping:
                            question_mapping[question_id] = {
                                "page": block["page"],
                                "x": float(block["x0"]),
                                "y": float(block["y0"]),
                                "text": text,
                                "question_type": question_type,
                            }
                            detected_questions.append(question_id)
                    except (ValueError, IndexError):
                        continue

        # Sort detected questions properly (numeric and alphanumeric)
        self.detected_questions = self._sort_questions(detected_questions)
        self.question_mapping = {str(q): question_mapping[q] for q in self.detected_questions}
        self.detected_questions = sorted(detected_questions)
        
        return self.question_mapping
    
    def _sort_questions(self, questions: List[str]) -> List[str]:
        """Sort questions in natural order (e.g., 1, 1a, 1b, 2, 2a, 2b, 3, etc.)"""
        def sort_key(q: str) -> Tuple[int, str]:
            # Extract main number and sub-letter
            match = re.match(r'^(\d+)([a-z])?$', str(q))
            if match:
                main_num = int(match.group(1))
                sub_letter = match.group(2) or ''
                return (main_num, sub_letter)
            return (999, q)

        return sorted(questions, key=sort_key)

    def get_question_mapping(self) -> Dict[str, Any]:
        """Return the detected question mapping."""
        return self.question_mapping

    def get_detected_question_count(self) -> int:
        """Return the count of detected questions."""
        return len(self.detected_questions)


class PDFMarker:
    """Marks PDF submissions with correct/incorrect indicators and score summary."""

    CHECKMARK = "✓"
    CROSSMARK = "✗"
    FONT_SIZE = 16
    MARK_COLOR = (0, 0, 0)
    CORRECT_COLOR = (0, 0.6, 0)
    INCORRECT_COLOR = (0.8, 0, 0)
    
    def __init__(self, pdf_path: str, output_path: str):
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is required for PDF processing. Install it with: pip install PyMuPDF")
        
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.doc = None
        self.question_mapping = {}
    
    def open_pdf(self) -> bool:
        """Open the PDF file for editing."""
        try:
            self.doc = fitz.open(self.pdf_path)
            return True
        except Exception as e:
            raise ValueError(f"Failed to open PDF: {str(e)}")
    
    def close_pdf(self):
        """Close the PDF document."""
        if self.doc:
            self.doc.close()
            self.doc = None
    
    def set_question_mapping(self, question_mapping: Dict[str, Any]):
        """Set the question position mapping."""
        self.question_mapping = question_mapping
    
    def overlay_marks(self, marks: Dict[str, bool]) -> bool:
        """
        Overlay checkmarks or cross marks on the PDF.

        Args:
            marks: Dictionary mapping question identifier (string) to True (correct) or False (incorrect)
                  Question identifiers can be: "1", "2", "1a", "1b", "2a", etc.
        """
        if not self.doc:
            self.open_pdf()

        try:
            for question_id, is_correct in marks.items():
                question_str = str(question_id)
                if question_str not in self.question_mapping:
                    continue

                question_info = self.question_mapping[question_str]
                page_num = question_info["page"]
                x = question_info["x"]
                y = question_info["y"]

                if page_num >= len(self.doc):
                    continue

                page = self.doc[page_num]
                mark_text = self.CHECKMARK if is_correct else self.CROSSMARK
                mark_color = self.CORRECT_COLOR if is_correct else self.INCORRECT_COLOR

                insertion_x = x + 250
                insertion_y = y - 3

                page.insert_text(
                    (insertion_x, insertion_y),
                    mark_text,
                    fontsize=self.FONT_SIZE,
                    color=mark_color,
                    fontname="helv-Bold"
                )

                page.insert_text(
                    (insertion_x + 20, insertion_y + 2),
                    "",
                    fontsize=self.FONT_SIZE - 4,
                    color=mark_color,
                    fontname="helv"
                )

            return True
        except Exception as e:
            raise ValueError(f"Failed to overlay marks: {str(e)}")
    
    def add_score_summary(self, driver_name: str, exam_title: str, correct_count: int, total_questions: int, exam_date: str = "") -> bool:
        """
        Add a score summary box to the first page of the PDF.

        Args:
            driver_name: Name of the driver
            exam_title: Title of the exam
            correct_count: Number of correct answers
            total_questions: Total number of questions
            exam_date: Date of the exam (optional)
        """
        if not self.doc or len(self.doc) == 0:
            self.open_pdf()

        try:
            page = self.doc[0]
            percentage = (correct_count / total_questions * 100) if total_questions > 0 else 0

            summary_lines = [
                "═" * 60,
                "EXAM MARKING SUMMARY",
                "═" * 60,
                f"Driver: {driver_name}",
                f"Exam: {exam_title}",
                f"Score: {correct_count}/{total_questions} ({percentage:.1f}%)",
            ]

            if exam_date:
                summary_lines.append(f"Date: {exam_date}")

            summary_lines.append("═" * 60)
            summary_lines.append("")
            summary_lines.append("Legend: ✓ = Correct Answer | ✗ = Incorrect Answer")
            summary_lines.append("═" * 60)

            y_pos = 30
            line_height = 22

            for i, line in enumerate(summary_lines):
                font_size = 13 if i in [1, 5] else 12
                font_weight = "helv-Bold" if i in [1, 5] else "helv"

                page.insert_text(
                    (40, y_pos),
                    line,
                    fontsize=font_size,
                    color=(0, 0, 0),
                    fontname=font_weight
                )
                y_pos += line_height

            return True
        except Exception as e:
            raise ValueError(f"Failed to add score summary: {str(e)}")
    
    def save_marked_pdf(self) -> bool:
        """Save the marked PDF to the output path."""
        try:
            if not self.doc:
                raise ValueError("No PDF document is open")
            
            os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
            self.doc.save(self.output_path)
            return True
        except Exception as e:
            raise ValueError(f"Failed to save marked PDF: {str(e)}")


def detect_questions_in_pdf(pdf_path: str) -> Tuple[Dict[int, Dict[str, Any]], int]:
    """
    Detect questions in a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        Tuple of (question_mapping, detected_count)
    """
    detector = PDFQuestionDetector(pdf_path)
    try:
        detector.open_pdf()
        question_mapping = detector.detect_questions()
        count = detector.get_detected_question_count()
        return question_mapping, count
    finally:
        detector.close_pdf()


def mark_pdf_submission(
    source_pdf: str,
    output_pdf: str,
    driver_name: str,
    exam_title: str,
    marks: Dict[int, bool],
    question_mapping: Dict[str, Any],
    exam_date: str = ""
) -> bool:
    """
    Create a marked PDF submission with overlaid marks and score summary.

    Args:
        source_pdf: Path to the original exam PDF
        output_pdf: Path where the marked PDF will be saved
        driver_name: Name of the driver
        exam_title: Title of the exam
        marks: Dictionary mapping question number to True (correct) or False (incorrect)
        question_mapping: Question position mapping from template
        exam_date: Date of the exam

    Returns:
        True if successful, False otherwise
    """
    marker = PDFMarker(source_pdf, output_pdf)
    try:
        marker.open_pdf()
        marker.set_question_mapping(question_mapping)

        correct_count = sum(1 for is_correct in marks.values() if is_correct)
        total_questions = len(marks)

        marker.overlay_marks(marks)
        marker.add_score_summary(driver_name, exam_title, correct_count, total_questions, exam_date)
        marker.save_marked_pdf()

        return True
    except Exception as e:
        raise ValueError(f"Error marking PDF: {str(e)}")
    finally:
        marker.close_pdf()


def generate_driver_detail_pdf(driver, submissions_data: List[Dict[str, Any]]) -> str:
    """
    Generate a comprehensive PDF report of a driver's profile and exam history.

    Args:
        driver: Driver instance
        submissions_data: List of submission data dictionaries

    Returns:
        Path to the generated PDF file
    """
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) is required for PDF processing. Install it with: pip install PyMuPDF")

    try:
        doc = fitz.open()
        page = doc.new_page()

        y_pos = 40
        line_height = 22
        section_height = 28

        header_color = (51, 126, 234)
        text_color = (0, 0, 0)

        page.insert_text(
            (40, y_pos),
            "DRIVER PROFILE & EXAM HISTORY REPORT",
            fontsize=18,
            color=header_color,
            fontname="helv-Bold"
        )
        y_pos += section_height

        page.insert_text(
            (40, y_pos),
            "─" * 90,
            fontsize=10,
            color=header_color,
        )
        y_pos += line_height

        page.insert_text(
            (40, y_pos),
            "DRIVER INFORMATION",
            fontsize=14,
            color=header_color,
            fontname="helv-Bold"
        )
        y_pos += line_height

        driver_info = [
            ("Name:", f"{driver.first_name} {driver.last_name}"),
            ("License No:", driver.license_no or "N/A"),
            ("Company:", driver.company or "N/A"),
            ("Batch:", driver.batch.name if driver.batch else "Not Assigned"),
            ("Phone:", driver.phone or "N/A"),
            ("Profile Created:", driver.created_at.strftime("%d-%m-%Y %H:%M")),
            ("Last Updated:", driver.updated_at.strftime("%d-%m-%Y %H:%M")),
        ]

        for label, value in driver_info:
            page.insert_text(
                (60, y_pos),
                f"{label}",
                fontsize=11,
                color=text_color,
                fontname="helv-Bold"
            )
            page.insert_text(
                (200, y_pos),
                str(value),
                fontsize=11,
                color=text_color,
                fontname="helv"
            )
            y_pos += line_height

        y_pos += section_height // 2

        page.insert_text(
            (40, y_pos),
            "─" * 90,
            fontsize=10,
            color=header_color,
        )
        y_pos += line_height

        page.insert_text(
            (40, y_pos),
            "EXAM SUBMISSION HISTORY",
            fontsize=14,
            color=header_color,
            fontname="helv-Bold"
        )
        y_pos += line_height

        if submissions_data:
            x_exam = 60
            x_date = 250
            x_score = 400
            x_status = 500

            page.insert_text(
                (x_exam, y_pos),
                "Exam Title",
                fontsize=10,
                color=header_color,
                fontname="helv-Bold"
            )
            page.insert_text(
                (x_date, y_pos),
                "Date",
                fontsize=10,
                color=header_color,
                fontname="helv-Bold"
            )
            page.insert_text(
                (x_score, y_pos),
                "Score",
                fontsize=10,
                color=header_color,
                fontname="helv-Bold"
            )
            page.insert_text(
                (x_status, y_pos),
                "Status",
                fontsize=10,
                color=header_color,
                fontname="helv-Bold"
            )
            y_pos += line_height

            page.insert_text(
                (40, y_pos),
                "─" * 90,
                fontsize=10,
                color=header_color,
            )
            y_pos += line_height

            for sub in submissions_data:
                submission = sub['submission']
                exam = sub['exam']

                exam_title = exam.title[:40]
                date_str = submission.created_at.strftime("%d-%m-%Y")
                score_str = f"{submission.score}/{exam.total_marks}" if submission.score else "Pending"
                status_str = sub['status']

                page.insert_text(
                    (x_exam, y_pos),
                    exam_title,
                    fontsize=10,
                    color=text_color,
                    fontname="helv"
                )
                page.insert_text(
                    (x_date, y_pos),
                    date_str,
                    fontsize=10,
                    color=text_color,
                    fontname="helv"
                )
                page.insert_text(
                    (x_score, y_pos),
                    score_str,
                    fontsize=10,
                    color=text_color,
                    fontname="helv"
                )

                status_color = (0, 128, 0) if status_str == "Scored" else (255, 140, 0)
                page.insert_text(
                    (x_status, y_pos),
                    status_str,
                    fontsize=10,
                    color=status_color,
                    fontname="helv-Bold"
                )
                y_pos += line_height

                if y_pos > 750:
                    page = doc.new_page()
                    y_pos = 40

            y_pos += line_height
        else:
            page.insert_text(
                (60, y_pos),
                "No submissions yet.",
                fontsize=11,
                color=text_color,
                fontname="helv"
            )
            y_pos += line_height

        page.insert_text(
            (40, y_pos),
            "─" * 90,
            fontsize=10,
            color=header_color,
        )
        y_pos += line_height

        page.insert_text(
            (40, y_pos),
            f"Report Generated: {timezone.now().strftime('%d-%m-%Y %H:%M:%S')}",
            fontsize=9,
            color=(128, 128, 128),
            fontname="helv"
        )

        output_path = os.path.join(
            tempfile.gettempdir(),
            f"driver_report_{driver.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )

        doc.save(output_path)
        doc.close()

        return output_path

    except Exception as e:
        raise ValueError(f"Error generating driver detail PDF: {str(e)}")
