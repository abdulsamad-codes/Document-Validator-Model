"""
Quick demo script: Run the DocumentSplitter on the real DGAM onboarding PDF.
No database or server needed - just pure CV and PDF splitting.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.preprocessing.splitter import DocumentSplitter

PDF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "demo", "TMA Khal Dir Lower .pdf"
)

print("=" * 60)
print("DOCUMENT SPLITTER - LIVE TEST")
print("=" * 60)
print(f"Input: {PDF_PATH}")
print()

with open(PDF_PATH, "rb") as f:
    results = DocumentSplitter.split_bulk_pdf(f)

print(f"✅ Total documents detected: {len(results)}")
print()
print("Breakdown:")
print("-" * 40)
for i, (doc_type, pdf_bytes) in enumerate(results, 1):
    size_kb = len(pdf_bytes) / 1024
    print(f"  {i}. {doc_type.value:<45} ({size_kb:.1f} KB)")

print()
print("=" * 60)
print("Done!")
