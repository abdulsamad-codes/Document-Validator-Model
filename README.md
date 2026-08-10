# 📄 Document Validator Model

> **KPITB Financial Document Verification System**
> An OCR-powered pipeline to validate onboarding documents submitted by sub-billers to KPITB (Khyber Pakhtunkhwa Information Technology Board).

---

## 🎯 Project Overview

This system automates the verification of official onboarding documents required when a department or organization registers as a **sub-biller** under the KPITB digital payment ecosystem (PayMin / Digital Muhasil).

The pipeline uses **OCR** to extract text from scanned/image-based PDFs, applies a **rule-based validation engine** to verify document compliance, performs **cross-document consistency checks**, and provides a **human review dashboard** for final approval.

---

## 📁 Project Structure

```
Document-Validator-Model/
│
├── main.py                              ← CLI entry point (start api / dashboard / tests)
├── config.py                            ← Central configuration (paths, thresholds)
├── requirements.txt                     ← Python dependencies
├── README.md                            ← This file
├── .gitignore
│
├── app/                                 ← Core Application Package
│   ├── __init__.py
│   │
│   ├── api/                             ← REST API Endpoints
│   │   └── endpoints.py                 ← All API routes (/health, /verify, /reports)
│   │
│   ├── database/                        ← Audit Logging
│   │   └── audit_logger.py              ← JSONL structured event logging for compliance
│   │
│   ├── pipeline/                        ← Document Processing Pipeline
│   │   ├── preprocessor.py              ← PDF detection & OpenCV image enhancement
│   │   ├── ocr_engine.py                ← OCR extraction (Tesseract / PaddleOCR)
│   │   ├── field_extractor.py           ← Regex + Pydantic structured field parsing
│   │   ├── stamp_signature_detector.py  ← Stamp, seal & signature detection (OpenCV)
│   │   └── orchestrator.py              ← End-to-end pipeline coordinator
│   │
│   ├── rules/                           ← Business Rule Engine
│   │   ├── base_rule.py                 ← Abstract rule interface
│   │   ├── document_rules.py            ← Per-document rule validators
│   │   └── rule_engine.py               ← Master rule evaluator, classifier & cross-doc matcher
│   │
│   ├── prompts/                         ← AI Reasoning Engine
│   │   └── reasoning_engine.txt         ← Structured prompt for human-review explanations
│   │
│   └── schemas/                         ← Pydantic Data Contracts
│       ├── document_schemas.py          ← Structured document field schemas
│       └── verification_schemas.py      ← Verification report response schemas
│
├── dashboard/                           ← Human Review UI (Streamlit MVP)
│   ├── app.py                           ← Streamlit dashboard application
│   └── components/                      ← Reusable UI components
│
├── frontend/                            ← React Dashboard (replaces Streamlit)
│   └── src/                             ← Vite + React + TypeScript SPA
│
├── scripts/                             ← Standalone Utilities
│   ├── extract_ocr_pdf.py               ← CLI OCR extraction tool
│   ├── extract_pdf_layers.py            ← PDF layer analysis
│   ├── recover_hidden_text.py           ← Blue overlay removal (OpenCV)
│   ├── remove_blue_layer.py             ← PDF annotation cleaner
│   ├── read_docx.py                     ← DOCX text extractor
│   └── generate_pdf.py                  ← Markdown-to-PDF converter
│
├── tests/                               ← Automated Test Suite (33/33 passing)
│   ├── test_preprocessor.py
│   ├── test_ocr_engine.py
│   ├── test_field_extractor.py
│   ├── test_rule_engine.py
│   ├── test_stamp_signature_detector.py
│   ├── test_orchestrator.py
│   └── test_audit_logger.py
│
├── data/                                ← Sample Data & Database
│   └── samples/                         ← Sample onboarding PDFs (gitignored)
│
├── docs/                                ← Documentation & Rule Base
│   ├── Master_Rules_Combined.md         ← Complete master business rules
│   └── ...
│
└── diagrams/                            ← Architecture & Flow Diagrams
    ├── document_feedback_flow.png
    └── system_architecture.png
```

---

## 📋 Documents Verified

| # | Document                                  | Key Checks                                                               |
| - | ----------------------------------------- | ------------------------------------------------------------------------ |
| 1 | **Authority Letter**                | Official letterhead, focal person named, signed & stamped                |
| 2 | **Account Maintenance Certificate** | Bank letterhead, format correct, bank details match across docs          |
| 3 | **Application Form**                | All fields filled, CNIC present, every page signed/stamped               |
| 4 | **Tripartite Agreement**            | 3 parties named, org name correct, bank details match, witnesses present |
| 5 | **Bilateral Agreement (SLA)**       | PayMin/Digital Muhasil mentioned, Section 5.2 charges, account match     |
| 6 | **E-Stamp Papers**                  | Brownish texture, watermark valid, notary public stamp                   |
| 7 | **Business Requirement Document**   | Lists all digitizable revenue services                                   |
| 8 | **Formal Request Letter**           | Subject: "Onboarding as sub-biller with KPITB"                           |
| 9 | **CNIC Copies**                     | All authorized persons' CNICs attached & legible                         |

---

## ⚙️ Tech Stack

| Component                  | Technology                        | Status     |
| -------------------------- | --------------------------------- | ---------- |
| **OCR**              | Tesseract (pytesseract)           | ✅ Shipped |
| **Image Processing** | OpenCV, Pillow                    | ✅ Shipped |
| **PDF Handling**     | PyMuPDF (fitz), pdf2image         | ✅ Shipped |
| **Data Schemas**     | Pydantic v2                       | ✅ Shipped |
| **API Server**       | FastAPI + Uvicorn                 | ✅ Shipped |
| **Dashboard**        | Streamlit + React (Vite)          | ✅ Shipped |
| **Object Detection** | YOLOv11 (stamp/signature)         | 🔜 Planned |
| **AI Reasoning**     | Qwen2.5-VL (mismatch explanation) | 🔜 Planned |

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/abdulsamad-codes/Document-Validator-Model.git
cd Document-Validator-Model

# Setup virtual environment
python -m venv Myenv
Myenv\Scripts\activate    # Windows
source Myenv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run API server
python main.py api

# Run dashboard (Streamlit)
python main.py dashboard

# Run full test suite
python main.py test
```

---

## 📖 Business Rules

See [`docs/Master_Rules_Combined.md`](docs/Master_Rules_Combined.md) for the complete set of verification rules.

---

## 📊 Pipeline Flow

```
Document Upload → PDF Layer Check → Image Enhancement → OCR Extraction
       → Structured Field Parsing → Stamp/Signature Detection
       → Cross-Document Matching → Business Rule Engine
       → Verification Report → Human Review Dashboard
```

---

## 🏢 Context

Developed during an internship at **KPITB** as part of the **Fintech Team's** digital payment onboarding automation initiative.

---

## 📄 License

This project is intended for internal use at KPITB. All rights reserved.
