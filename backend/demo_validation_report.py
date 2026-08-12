"""
Generate a temporary OCR extraction and validation report.
Reads the first 3 pages of the TMA Khal PDF and outputs the raw OCR text.
"""
import sys
import os
import pymupdf as fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.preprocessing.splitter import DocumentSplitter

PDF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "demo", "TMA Khal Dir Lower .pdf"
)

print("# Temporary Validation & OCR Report")
print(f"**Document**: `{os.path.basename(PDF_PATH)}`\n")

doc = fitz.open(PDF_PATH)
num_pages = min(3, len(doc)) # Only check first 3 pages for speed

for page_num in range(num_pages):
    page = doc.load_page(page_num)
    
    print(f"## Page {page_num + 1}")
    text = page.get_text().strip().upper()
    
    if len(text) < 30:
        print("*(Image-based page detected. Running PaddleOCR...)*\n")
        text = DocumentSplitter._ocr_page(page)
    
    print("### Extracted Text (First 1000 chars)")
    print("```text")
    print(text[:1000] if text else "[No text extracted]")
    print("```\n")
    
    detected_type = DocumentSplitter._classify_text(text)
    print(f"**Classification Result**: `{detected_type.name if detected_type else 'OTHER_SUPPORTING_DOCUMENT'}`\n")
    print("---")

doc.close()
