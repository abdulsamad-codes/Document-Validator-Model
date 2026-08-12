"""
Image Enhancement Module.

Provides Computer Vision based utilities to enhance scanned document images
before OCR extraction or splitting. Includes deskewing, CLAHE, and denoising.
"""

import cv2
import numpy as np

class ImageEnhancer:
    """Enhances images for better OCR and structural analysis."""

    @staticmethod
    def enhance_for_ocr(image: np.ndarray) -> np.ndarray:
        """
        Applies standard image enhancements for better OCR accuracy.
        - Grayscale conversion
        - CLAHE (Contrast Limited Adaptive Histogram Equalization)
        - Denoising
        """
        # Convert to grayscale if it has 3 channels
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        # Apply CLAHE to improve contrast in unevenly lit scans
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Denoise slightly to remove background static
        denoised = cv2.fastNlMeansDenoising(enhanced, None, h=10, templateWindowSize=7, searchWindowSize=21)
        
        # Convert back to 3-channel image for OCR models that expect RGB/BGR input
        denoised_bgr = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
        
        return denoised_bgr

    @staticmethod
    def deskew_image(image: np.ndarray) -> np.ndarray:
        """
        Detects text skew and rotates the image to straighten it.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
        
        # Invert colors (text white, background black) for thresholding
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        # Get coordinates of all text pixels
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) == 0:
            return image
            
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
        rotated = cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255)
        )
        
        return rotated
