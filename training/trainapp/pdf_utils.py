import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

try:
    import fitz
except ImportError:
    fitz = None


class PDFQuestionDetector:
    """Detects question positions in PDF files using text extraction and regex patterns."""
    
    QUESTION_PATTERNS = [
        r'^\s*(\d+)\s*[\.\):\-]\s*',
        r'^\s*Q(\d+)\s*[\.\):\-]\s*',
        r'^\s*Question\s+(\d+)\s*[\.\):\-]\s*',
        r'^\s*\((\d+)\)\s*',
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
    
    def detect_questions(self) -> Dict[int, Dict[str, Any]]:
        """Detect question numbers and their positions in the PDF."""
        text_blocks = self.extract_text_with_coordinates()
        
        question_mapping = {}
        detected_questions = []
        
        for block in text_blocks:
            text = block["text"]
            for pattern in self.QUESTION_PATTERNS:
                match = re.match(pattern, text)
                if match:
                    try:
                        question_num = int(match.group(1))
                        if question_num not in question_mapping:
                            question_mapping[question_num] = {
                                "page": block["page"],
                                "x": float(block["x0"]),
                                "y": float(block["y0"]),
                                "text": text,
                            }
                            detected_questions.append(question_num)
                    except (ValueError, IndexError):
                        continue
        
        self.question_mapping = {str(q): question_mapping[q] for q in sorted(question_mapping.keys())}
        self.detected_questions = sorted(detected_questions)
        
        return self.question_mapping
    
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
    
    def overlay_marks(self, marks: Dict[int, bool]) -> bool:
        """
        Overlay checkmarks or cross marks on the PDF.
        
        Args:
            marks: Dictionary mapping question number to True (correct) or False (incorrect)
        """
        if not self.doc:
            self.open_pdf()
        
        try:
            for question_num, is_correct in marks.items():
                question_str = str(question_num)
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
                "═" * 50,
                "EXAM MARKING SUMMARY",
                "═" * 50,
                f"Driver: {driver_name}",
                f"Exam: {exam_title}",
                f"Score: {correct_count}/{total_questions} ({percentage:.1f}%)",
            ]
            
            if exam_date:
                summary_lines.append(f"Date: {exam_date}")
            
            summary_lines.append("═" * 50)
            
            y_pos = 50
            line_height = 20
            
            for line in summary_lines:
                page.insert_text(
                    (50, y_pos),
                    line,
                    fontsize=11,
                    color=(0, 0, 0),
                    fontname="helv"
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
