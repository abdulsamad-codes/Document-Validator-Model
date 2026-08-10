import pytest
import numpy as np
import cv2
from app.pipeline.stamp_signature_detector import StampSignatureDetector


@pytest.fixture
def detector():
    return StampSignatureDetector()


@pytest.fixture
def image_with_blue_stamp():
    """Create a dummy image with a blue circle (stamp)"""
    img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    # Draw a blue circle (BGR format: Blue, Green, Red)
    cv2.circle(img, (250, 250), 50, (255, 0, 0), -1)
    return img


@pytest.fixture
def image_with_signature():
    """Create a dummy image with a squiggly wide line (signature)"""
    img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    # Draw a wide squiggly black line
    pts = np.array([[100, 300], [150, 280], [200, 320], [250, 290], [300, 310], [350, 280]], np.int32)
    pts = pts.reshape((-1, 1, 2))
    cv2.polylines(img, [pts], False, (0, 0, 0), 3)
    return img


def test_detect_stamp(detector, image_with_blue_stamp):
    """Test stamp detection logic based on color and circularity"""
    result = detector.detect_stamp(image_with_blue_stamp)
    
    assert result["is_present"] is True
    assert result["bounding_box"] is not None
    # Check bounding box approximately matches the drawn circle
    x, y, w, h = result["bounding_box"]
    assert 190 <= x <= 210
    assert 190 <= y <= 210
    assert 90 <= w <= 110
    assert 90 <= h <= 110


def test_detect_no_stamp(detector):
    """Test stamp detection returns false on blank image"""
    blank_img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    result = detector.detect_stamp(blank_img)
    
    assert result["is_present"] is False


def test_detect_signature(detector, image_with_signature):
    """Test signature detection heuristics (aspect ratio, density)"""
    result = detector.detect_signature(image_with_signature)
    
    assert result["is_present"] is True
    assert result["bounding_box"] is not None


def test_detect_no_signature(detector):
    """Test signature detection returns false on blank image"""
    blank_img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    result = detector.detect_signature(blank_img)
    
    assert result["is_present"] is False
