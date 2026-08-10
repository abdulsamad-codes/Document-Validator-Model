#!/usr/bin/env python3
"""
Extract text from scanned/image-based PDFs using OCR
Works when PDFs contain images instead of text layers
"""

from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import sys
import argparse
from pathlib import Path

# ============================================================================
# METHOD: OCR - Extract text from scanned PDF pages
# ============================================================================

def extract_text_ocr(pdf_path, page_num=0, output_txt=None):
    """
    Extract text from scanned PDF using OCR (Tesseract)
    page_num: 0-indexed (0 = first page)
    """
    print(f"\n{'='*70}")
    print(f"OCR TEXT EXTRACTION FROM SCANNED PDF")
    print(f"{'='*70}\n")
    
    try:
        # Convert PDF page to image
        print(f"Converting PDF page {page_num + 1} to image...")
        images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1, dpi=300)
        
        if not images:
            print("✗ Could not convert PDF to image")
            return None
        
        img = images[0]
        print(f"✓ Image created: {img.size}")
        
        # Extract text using OCR
        print(f"\nRunning OCR (this may take a moment)...")
        text = pytesseract.image_to_string(img, lang='eng')
        
        if text.strip():
            print(f"\n✓ TEXT EXTRACTED FROM PAGE {page_num + 1}:")
            print("-" * 70)
            print(text)
            print("-" * 70)
            
            # Save to file if specified
            if output_txt:
                with open(output_txt, 'w', encoding='utf-8') as f:
                    f.write(text)
                print(f"\n✓ Saved to: {output_txt}")
            
            return text
        else:
            print("⚠ No text found on this page (page may be blank or unreadable)")
            return None
    
    except Exception as e:
        print(f"✗ Error: {e}")
        print("\n✓ SOLUTION: Install required packages:")
        print("  pip install --break-system-packages pdf2image pytesseract")
        print("\n✓ Also requires system packages:")
        print("  Ubuntu/Debian: sudo apt-get install poppler-utils tesseract-ocr")
        return None


def extract_all_pages_ocr(pdf_path, output_dir="extracted_ocr"):
    """
    Extract text from ALL pages using OCR and save individually
    """
    print(f"\n{'='*70}")
    print(f"OCR EXTRACTION - ALL PAGES")
    print(f"{'='*70}\n")
    
    try:
        # Create output directory
        Path(output_dir).mkdir(exist_ok=True)
        
        # Convert all pages to images
        print(f"Converting all PDF pages to images (DPI: 300)...")
        images = convert_from_path(pdf_path, dpi=300)
        print(f"✓ Converted {len(images)} pages\n")
        
        all_texts = {}
        
        for i, img in enumerate(images):
            page_num = i + 1
            print(f"[{page_num}/{len(images)}] Running OCR on page {page_num}...", end=" ")
            
            text = pytesseract.image_to_string(img, lang='eng')
            all_texts[f"page_{page_num}"] = text
            
            # Save individual page
            page_file = f"{output_dir}/page_{page_num}.txt"
            with open(page_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
            char_count = len(text.strip())
            print(f"✓ ({char_count} chars)")
        
        # Save combined file
        combined_file = f"{output_dir}/COMBINED_ALL_PAGES.txt"
        with open(combined_file, 'w', encoding='utf-8') as f:
            for page_num, text in all_texts.items():
                f.write(f"\n{'='*70}\n")
                f.write(f"{page_num.upper()}\n")
                f.write(f"{'='*70}\n\n")
                f.write(text)
                f.write("\n\n")
        
        print(f"\n✓ All pages saved to: {output_dir}/")
        print(f"✓ Combined file: {combined_file}")
        
        return all_texts
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract text from a scanned/image-based PDF using OCR."
    )
    parser.add_argument(
        "pdf_file",
        nargs="?",
        default=None,
        help="Path to the input PDF file (required)."
    )
    parser.add_argument(
        "--output-txt",
        default="PAGE1_output.txt",
        help="Output .txt file for the first page (default: PAGE1_output.txt)."
    )
    parser.add_argument(
        "--output-dir",
        default="extracted_ocr_pages",
        help="Output directory for all pages (default: ./extracted_ocr_pages)."
    )
    args = parser.parse_args()

    if not args.pdf_file:
        parser.print_help()
        print("\nError: pdf_file argument is required.")
        sys.exit(1)

    pdf_file = args.pdf_file

    if not Path(pdf_file).exists():
        print(f"Error: File not found: {pdf_file}")
        sys.exit(1)

    print(f"\n{'#'*70}")
    print(f"# OCR TEXT EXTRACTION - SCANNED/IMAGE-BASED PDF")
    print(f"# File: {pdf_file}")
    print(f"{'#'*70}")

    # Extract from first page (Authority Letter with hidden text)
    extract_text_ocr(
        pdf_file,
        page_num=0,  # First page
        output_txt=args.output_txt
    )

    # Extract all pages
    extract_all_pages_ocr(
        pdf_file,
        output_dir=args.output_dir
    )

    print("\nOCR extraction complete!")
