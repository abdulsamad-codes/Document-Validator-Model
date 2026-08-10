"""
Central Configuration for the Document Verification System.

All settings, paths, and thresholds are managed here.
"""

import os
from pathlib import Path


# ============================================================================
# PROJECT PATHS
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = DATA_DIR / "samples"
DOCS_DIR = BASE_DIR / "docs"
LOGS_DIR = BASE_DIR / "logs"

# ============================================================================
# OCR CONFIGURATION
# ============================================================================
OCR_ENGINE = os.getenv("OCR_ENGINE", "tesseract")  # "tesseract" or "paddleocr"
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+urd")
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.70"))

# ============================================================================
# IMAGE PREPROCESSING
# ============================================================================
DESKEW_ENABLED = True
DENOISE_ENABLED = True
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)
BINARY_THRESHOLD = 150

# ============================================================================
# STAMP & SIGNATURE DETECTION
# ============================================================================
STAMP_MIN_AREA = 500         # Minimum contour area to consider as a stamp
STAMP_CIRCULARITY = 0.5      # Minimum circularity ratio for stamp detection
SIGNATURE_MIN_AREA = 200     # Minimum contour area for signature detection

# ============================================================================
# CROSS-DOCUMENT MATCHING
# ============================================================================
FUZZY_MATCH_THRESHOLD = 0.85  # Minimum similarity ratio for fuzzy name matching
EXACT_MATCH_FIELDS = [        # Fields that require exact (not fuzzy) matching
    "account_number",
    "iban",
    "cnic_number",
]

# ============================================================================
# VERIFICATION RESULT CLASSIFICATIONS
# ============================================================================
class VerificationStatus:
    PASS = "PASS"
    WARNING = "WARNING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAIL = "FAIL"
    REJECTED = "REJECTED"

# ============================================================================
# DATABASE (for future use)
# ============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'data' / 'verification.db'}"
)

# ============================================================================
# API SERVER
# ============================================================================
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
