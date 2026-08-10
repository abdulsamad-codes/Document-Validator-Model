"""
OCR Engine Module.

Provides a unified interface for extracting text from images using PyTesseract.
(Designed to be extended with PaddleOCR as per the architecture spec).
"""

import cv2
import numpy as np
import pytesseract
import logging
from typing import Dict, List, Optional
from config import OCR_LANGUAGES, OCR_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


class OCREngine:
    def __init__(self, engine_type: str = "tesseract"):
        self.engine_type = engine_type
        # In a real environment, you might need to set pytesseract.pytesseract.tesseract_cmd

    def extract_text(self, image: np.ndarray) -> str:
        """
        Extract raw text from an image.
        """
        try:
            if len(image.shape) == 3:
                # Tesseract works best with RGB, OpenCV is BGR
                img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                img_rgb = image
                
            text = pytesseract.image_to_string(img_rgb, lang=OCR_LANGUAGES)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR text extraction failed: {e}")
            raise RuntimeError(f"OCR text extraction failed: {e}")

    def extract_data(self, image: np.ndarray) -> Dict:
        """
        Extract detailed data including bounding boxes and confidences.
        Returns a dictionary compatible with pytesseract.image_to_data(output_type=Output.DICT).
        """
        try:
            if len(image.shape) == 3:
                img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                img_rgb = image
                
            data = pytesseract.image_to_data(img_rgb, lang=OCR_LANGUAGES, output_type=pytesseract.Output.DICT)
            return data
        except Exception as e:
            logger.error(f"OCR data extraction failed: {e}")
            raise RuntimeError(f"OCR data extraction failed: {e}")

    def get_average_confidence(self, ocr_data: Dict) -> float:
        """
        Calculate the average confidence of the extracted text.
        """
        confidences = ocr_data.get('conf', [])
        # Tesseract returns '-1' for empty/invalid blocks
        valid_confs = [float(c) for c in confidences if c != '-1' and c != -1]
        
        if not valid_confs:
            return 0.0
            
        return sum(valid_confs) / len(valid_confs) / 100.0  # Normalized to 0.0 - 1.0

    def is_readable(self, ocr_data: Dict) -> bool:
        """
        Determines if the document is readable based on the configured threshold.
        """
        return self.get_average_confidence(ocr_data) >= OCR_CONFIDENCE_THRESHOLD
