"""
Image and PDF Preprocessing Module.

Handles PDF to image conversion, text layer detection, deskewing,
and OpenCV-based image enhancements (CLAHE, denoise) before OCR.
"""

import cv2
import numpy as np
import fitz  # PyMuPDF
from typing import List, Tuple, Union
from pathlib import Path


class Preprocessor:
    def __init__(self, config=None):
        """Initialize with optional configuration dict/object."""
        self.config = config or {}

    def extract_images_from_pdf(self, pdf_path: Union[str, Path], dpi: int = 300) -> List[np.ndarray]:
        """
        Converts a PDF file to a list of OpenCV images (numpy arrays).
        """
        pdf_path = str(pdf_path)
        images = []
        try:
            doc = fitz.open(pdf_path)
            # Zoom matrix for DPI
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # Convert fitz pixmap to numpy array (RGB)
                img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                
                # Convert RGB to BGR for OpenCV
                if pix.n == 3:
                    img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
                elif pix.n == 1:
                    img_bgr = cv2.cvtColor(img_data, cv2.COLOR_GRAY2BGR)
                else:
                    img_bgr = img_data
                
                images.append(img_bgr)
            doc.close()
            return images
        except Exception as e:
            raise RuntimeError(f"Failed to extract images from PDF: {e}")

    def is_scanned_pdf(self, pdf_path: Union[str, Path]) -> bool:
        """
        Determines if a PDF is a scanned document (mostly images, little/no text layer)
        or a digital document.
        Returns True if scanned, False if digital.
        """
        try:
            doc = fitz.open(str(pdf_path))
            total_text_length = 0
            image_count = 0
            
            for page in doc:
                text = page.get_text().strip()
                total_text_length += len(text)
                image_count += len(page.get_images(full=True))
            
            doc.close()
            
            # Heuristic: If it has very little text but has images, it's a scan.
            if total_text_length < 100 and image_count > 0:
                return True
            return False
        except Exception as e:
            raise RuntimeError(f"Failed to analyze PDF type: {e}")

    def enhance_image_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Applies standard image enhancements for better OCR accuracy.
        - Grayscale conversion
        - CLAHE (Contrast Limited Adaptive Histogram Equalization)
        - Denoising
        """
        # 1. Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # 2. Apply CLAHE to improve contrast in unevenly lit scans
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # 3. Denoise slightly to remove background static
        denoised = cv2.fastNlMeansDenoising(enhanced, None, h=10, templateWindowSize=7, searchWindowSize=21)
        
        return denoised

    def deskew_image(self, image: np.ndarray) -> np.ndarray:
        """
        Detects text skew and rotates the image to straighten it.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
        
        # Invert colors (text white, background black) for thresholding
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        # Get coordinates of all text pixels
        coords = np.column_stack(np.where(thresh > 0))
        
        # Get minimum bounding box and angle
        angle = cv2.minAreaRect(coords)[-1]
        
        # OpenCV minAreaRect angle adjustment
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
            
        # If angle is very small, ignore (probably already straight)
        if abs(angle) < 0.5:
            return image
            
        # Rotate image
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Use white background for rotation padding
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        
        return rotated
