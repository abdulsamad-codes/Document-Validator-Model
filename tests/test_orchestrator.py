import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from pathlib import Path
from app.pipeline.orchestrator import PipelineOrchestrator
from app.schemas.document_schemas import DocumentType


@pytest.fixture
def orchestrator():
    return PipelineOrchestrator()


@patch('app.pipeline.ocr_engine.pytesseract.image_to_string')
@patch('app.pipeline.preprocessor.fitz')
def test_process_document_tripartite(mock_fitz, mock_ocr, orchestrator, tmp_path):
    """Test that the orchestrator correctly populates a TripartiteData schema."""
    # Create a fake PDF
    fake_pdf = tmp_path / "test_tripartite.pdf"
    fake_pdf.write_bytes(b"%PDF-1.0 fake content")
    
    # Mock fitz (PyMuPDF) to return a dummy image
    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.h = 100
    mock_pix.w = 200
    mock_pix.n = 3
    mock_pix.samples = np.ones((100, 200, 3), dtype=np.uint8).tobytes()
    mock_page.get_pixmap.return_value = mock_pix
    mock_doc.load_page.return_value = mock_page
    mock_doc.__len__ = MagicMock(return_value=1)
    mock_fitz.open.return_value = mock_doc
    mock_fitz.Matrix.return_value = MagicMock()
    
    # Mock OCR output
    mock_ocr.return_value = "This is a Tripartite Agreement. IBAN: PK12ABCD1234567890123456"
    
    result = orchestrator.process_document(fake_pdf, DocumentType.TRIPARTITE)
    
    assert result.document_type == DocumentType.TRIPARTITE
    assert result.file_name == "test_tripartite.pdf"
    assert result.tripartite is not None


@patch('app.pipeline.ocr_engine.pytesseract.image_to_string')
@patch('app.pipeline.preprocessor.fitz')
def test_process_document_bilateral(mock_fitz, mock_ocr, orchestrator, tmp_path):
    """Test bilateral document processing populates platform mention."""
    fake_pdf = tmp_path / "bilateral.pdf"
    fake_pdf.write_bytes(b"%PDF-1.0 fake content")
    
    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.h = 100
    mock_pix.w = 200
    mock_pix.n = 3
    mock_pix.samples = np.ones((100, 200, 3), dtype=np.uint8).tobytes()
    mock_page.get_pixmap.return_value = mock_pix
    mock_doc.load_page.return_value = mock_page
    mock_doc.__len__ = MagicMock(return_value=1)
    mock_fitz.open.return_value = mock_doc
    mock_fitz.Matrix.return_value = MagicMock()
    
    mock_ocr.return_value = "This Bilateral Agreement mentions Digital Muhasil platform."
    
    result = orchestrator.process_document(fake_pdf, DocumentType.BILATERAL)
    
    assert result.document_type == DocumentType.BILATERAL
    assert result.bilateral is not None
    assert result.bilateral.platform_mentioned == "Digital Muhasil"
