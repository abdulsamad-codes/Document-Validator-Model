# 📄 Document Validator Model

> **KPITB Fintech Document Verification System**  
> An OCR-powered pipeline to validate onboarding documents submitted by sub-billers to KPITB (Khyber Pakhtunkhwa Information Technology Board).

---

## 🎯 Project Overview

This project automates the validation of official onboarding documents required when a department or organization registers as a **sub-biller** under the KPITB digital payment ecosystem (PayMin / Digital Muhasil).

The system uses **OCR (Optical Character Recognition)** to extract text from scanned/image-based PDFs and applies a rule-based validation engine to verify document compliance.

---

## 📁 Project Structure

```
Document-Validator-Model/
├── README.md                        ← This file
├── .gitignore                       ← Git ignore rules
├── requirements.txt                 ← Python dependencies
│
├── docs/                            ← Documentation & Rules
│   ├── Extracted_Rules.md           ← Validation rules (plain English)
│   ├── COMPLETE_PDF_EXTRACTION_GUIDE.md  ← OCR extraction guide
│   └── checklist.md                 ← Manual verification checklist
│
├── scripts/                         ← Python processing scripts
│   ├── extract_ocr_pdf.py           ← Main OCR extraction (all pages)
│   ├── extract_pdf_layers.py        ← PDF layer analysis & annotation removal
│   ├── recover_hidden_text.py       ← Recover text hidden by blue overlay
│   ├── remove_blue_layer.py         ← Remove blue annotation layer from PDFs
│   └── read_docx.py                 ← Read and extract text from .docx files
│
└── diagrams/                        ← Architecture & Flow Diagrams
    ├── document_feedback_flow.png   ← Document feedback flow diagram
    └── system_architecture.png      ← Overall system architecture
```

---

## 📋 Documents Being Validated

| # | Document | Key Rules |
|---|----------|-----------|
| 1 | **Authority Letter** | Official letterhead, signed & stamped, focal person named |
| 2 | **Account Maintenance Certificate** | Standard format, bank-signed, matches bank details in agreements |
| 3 | **Application Form** | All fields filled, CNIC present, every page signed/stamped |
| 4 | **Tripartite Agreement** | Correct org name, bank details match, all 3-party signatures |
| 5 | **Bilateral Agreement (SLA)** | Mentions PayMin/Digital Muhasil, correct account numbers, Section 5.2 complete |
| 6 | **E-Stamp Papers** | Correct texture/watermark, accurate first/second party details |
| 7 | **Business Requirement Document** | Lists all digitizable revenue services |
| 8 | **Formal Request Letter** | Correct subject: "Onboarding as sub-biller with KPITB" |
| 9 | **CNIC Copies** | CNICs of all authorized persons attached |

---

## ⚙️ Tech Stack

- **Python 3.x**
- **PyMuPDF (`fitz`)** — PDF layer extraction, annotation removal
- **pytesseract** — OCR text extraction (Tesseract engine)
- **pdf2image** — PDF-to-image conversion for OCR
- **OpenCV (`cv2`)** — Image preprocessing (overlay removal, thresholding)
- **Pillow (PIL)** — Image handling

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/abdulsamad-codes/Document-Validator-Model.git
cd Document-Validator-Model
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install System Dependencies

**Windows:**
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/)

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

**macOS:**
```bash
brew install tesseract poppler
```

### 4. Run OCR Extraction
```bash
# Extract text from all pages of a scanned PDF
python scripts/extract_ocr_pdf.py

# Remove blue annotation overlays from a PDF
python scripts/remove_blue_layer.py

# Analyze PDF layers and extract images
python scripts/extract_pdf_layers.py
```

---

## 📖 Validation Rules

See [`docs/Extracted_Rules.md`](docs/Extracted_Rules.md) for the complete set of document validation rules.

---

## 📊 Pipeline Flow

```
Scanned PDF
    │
    ▼
[PDF Layer Analysis]          ← extract_pdf_layers.py
    │  Checks for text layers, extracts image layers
    │
    ▼
[Blue Overlay Removal]        ← remove_blue_layer.py / recover_hidden_text.py
    │  Removes annotation stamps blocking text
    │
    ▼
[OCR Text Extraction]         ← extract_ocr_pdf.py
    │  Converts pages to images → runs Tesseract OCR
    │
    ▼
[Rule-Based Validation]       ← (validation engine — in development)
    │  Checks each document against Extracted_Rules.md
    │
    ▼
[Validation Report]
    Flags missing fields, mismatched data, incomplete signatures
```

---

## 🏢 Context

This project was developed during an internship at **KPITB (Khyber Pakhtunkhwa Information Technology Board)** as part of the **Fintech Team's** digital payment onboarding process automation initiative.

---

## 📄 License

This project is intended for internal use at KPITB. All rights reserved.
