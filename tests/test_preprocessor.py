import pytest
import numpy as np
import cv2
from pathlib import Path
from app.pipeline.preprocessor import Preprocessor

# Create a temporary directory for tests
TEST_DIR = Path(__file__).parent / "test_data"
TEST_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def preprocessor():
    return Preprocessor()


@pytest.fixture
def sample_image():
    """Create a sample OpenCV image (white background with black text/shapes)"""
    img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    # Draw a black rectangle to represent text block
    cv2.rectangle(img, (100, 100), (400, 200), (0, 0, 0), -1)
    return img


@pytest.fixture
def skewed_image():
    """Create an intentionally skewed image"""
    img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    # Draw a rotated rectangle
    center = (250, 250)
    size = (300, 100)
    angle = 15  # 15 degrees skew
    rect = (center, size, angle)
    box = cv2.boxPoints(rect)
    box = np.int32(box)
    cv2.drawContours(img, [box], 0, (0, 0, 0), -1)
    return img


def test_enhance_image(preprocessor, sample_image):
    """Test image enhancement (CLAHE, denoise)"""
    enhanced = preprocessor.enhance_image_for_ocr(sample_image)
    
    # Should return a grayscale/single-channel image
    assert len(enhanced.shape) == 2, "Enhanced image should be 2D (grayscale)"
    assert enhanced.shape[0] == sample_image.shape[0]
    assert enhanced.shape[1] == sample_image.shape[1]


def test_deskew_image(preprocessor, skewed_image):
    """Test image deskewing"""
    # The deskew_image function should rotate the image back to near 0 degrees
    deskewed = preprocessor.deskew_image(skewed_image)
    
    # It should have the same dimensions
    assert deskewed.shape == skewed_image.shape
    
    # Verify the rectangle is now mostly straight
    gray = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY) if len(deskewed.shape) == 3 else deskewed.copy()
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    angle = cv2.minAreaRect(coords)[-1]
    
    # Adjust OpenCV angle logic
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
        
    # The angle should now be close to 0
    assert abs(angle) < 5.0, f"Deskew failed, angle is {angle}"


def test_is_scanned_pdf_handles_missing_file(preprocessor):
    """Test PDF scan detection handles missing files gracefully"""
    with pytest.raises(RuntimeError) as exc_info:
        preprocessor.is_scanned_pdf("nonexistent_file.pdf")
    assert "Failed to analyze PDF type" in str(exc_info.value)
