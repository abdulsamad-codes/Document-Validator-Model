"""
Stamp and Signature Detection Module.

Uses OpenCV heuristics to detect the presence of official stamps,
notary seals, and signatures in a document image.
"""

import cv2
import numpy as np
from typing import List, Tuple, Dict
from config import STAMP_MIN_AREA, STAMP_CIRCULARITY, SIGNATURE_MIN_AREA


class StampSignatureDetector:
    def __init__(self):
        pass

    def detect_stamp(self, image: np.ndarray) -> Dict:
        """
        Detects potential official stamps based on color (blue/red/purple)
        and circularity/contour shape.
        Returns a dict with 'is_present' and 'bounding_box'.
        """
        # A simple heuristic: official stamps are often blue, red, or purple.
        # We can try to detect significant non-black/non-white components.
        
        # 1. Convert to HSV
        if len(image.shape) != 3:
            # If grayscale, we can't use color heuristics effectively, 
            # fallback to looking for large round-ish contours
            return self._detect_stamp_grayscale(image)
            
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # 2. Define color ranges for common stamps (Blue, Red/Purple)
        # Blue range
        lower_blue = np.array([100, 50, 50])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # Red ranges (wraps around in HSV)
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        
        lower_red2 = np.array([170, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        
        # Combine masks
        mask = cv2.bitwise_or(mask_blue, cv2.bitwise_or(mask_red1, mask_red2))
        
        # 3. Find contours in the mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 4. Filter contours by area and shape
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > STAMP_MIN_AREA:
                perimeter = cv2.arcLength(contour, True)
                if perimeter == 0:
                    continue
                    
                circularity = 4 * np.pi * (area / (perimeter * perimeter))
                
                # Stamps are often circular or oval
                if circularity > STAMP_CIRCULARITY:
                    x, y, w, h = cv2.boundingRect(contour)
                    return {
                        "is_present": True,
                        "bounding_box": [x, y, w, h],
                        "is_readable": False # Requires OCR specifically on this box to determine
                    }
                    
        return {"is_present": False, "bounding_box": None, "is_readable": False}

    def _detect_stamp_grayscale(self, image: np.ndarray) -> Dict:
        """Fallback for grayscale images: looks for circular/large connected components."""
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Threshold and invert
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        
        # Morphological close to connect stamp parts
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > STAMP_MIN_AREA * 2: # Stricter area for grayscale
                perimeter = cv2.arcLength(contour, True)
                if perimeter > 0:
                    circularity = 4 * np.pi * (area / (perimeter * perimeter))
                    if circularity > STAMP_CIRCULARITY:
                        x, y, w, h = cv2.boundingRect(contour)
                        return {
                            "is_present": True,
                            "bounding_box": [x, y, w, h],
                            "is_readable": False
                        }
        
        return {"is_present": False, "bounding_box": None, "is_readable": False}

    def detect_signature(self, image: np.ndarray) -> Dict:
        """
        Detects potential signatures using contour heuristics
        (squiggly lines, specific aspect ratios).
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
        
        # Threshold to get dark text/lines
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            # Signatures tend to have a moderate area but large bounding boxes (low density)
            if area > SIGNATURE_MIN_AREA:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Aspect ratio (signatures are usually wider than they are tall)
                aspect_ratio = float(w) / h if h > 0 else 0
                
                # Bounding box density (pixels / bounding box area)
                density = area / (w * h) if w * h > 0 else 0
                
                # Heuristics: wide, low density (lots of whitespace inside bounding box), decent size
                if 1.5 < aspect_ratio < 6.0 and 0.05 < density < 0.4:
                    return {
                        "is_present": True,
                        "bounding_box": [x, y, w, h]
                    }
                    
        return {"is_present": False, "bounding_box": None}
