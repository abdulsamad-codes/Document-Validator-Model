import pytest
import numpy as np
import cv2
from unittest.mock import patch
from app.pipeline.ocr_engine import OCREngine
import pytesseract


@pytest.fixture
def ocr_engine():
    return OCREngine()


@pytest.fixture
def dummy_image():
    """Create a dummy image for testing."""
    return np.ones((100, 300, 3), dtype=np.uint8) * 255


def test_get_average_confidence(ocr_engine):
    """Test confidence calculation ignores -1 values"""
    mock_data = {
        'conf': ['-1', 95, 85, '-1', 90]
    }
    
    # Average of 95, 85, 90 is 90.0, normalized is 0.90
    avg_conf = ocr_engine.get_average_confidence(mock_data)
    assert np.isclose(avg_conf, 0.90)


def test_is_readable(ocr_engine):
    """Test readability threshold logic"""
    # Assuming config threshold is 0.70
    good_data = {'conf': [80, 90, 85]}
    bad_data = {'conf': [40, 50, 45]}
    
    assert ocr_engine.is_readable(good_data) == True
    assert ocr_engine.is_readable(bad_data) == False


@patch('pytesseract.image_to_string')
def test_extract_text_mocked(mock_image_to_string, ocr_engine, dummy_image):
    """Test extract_text with a mocked tesseract call to avoid system dependency issues"""
    mock_image_to_string.return_value = "Hello World"
    
    result = ocr_engine.extract_text(dummy_image)
    assert result == "Hello World"
    mock_image_to_string.assert_called_once()
