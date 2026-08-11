"""Configuration for the document processing module.

Centralizes the document source classification, the processing methods and OCR
engine identifiers, and the thresholds that drive routing and timeout behaviour.
The service and processor code consume these constants, so tuning a threshold or
adding a processing method never requires touching the route or schema layers.
"""

from enum import Enum

from app.technical_validation.constants import FileFormat


class DocumentSource(str, Enum):
    """How a document's text is most reliably obtained.

    A PDF is ``DIGITAL_PDF`` when it already carries selectable text (extracted
    directly with PyMuPDF) and ``SCANNED_PDF`` when its pages are images that
    must be OCR'd. Non-PDF formats are ``IMAGE`` documents.
    """

    DIGITAL_PDF = "DIGITAL_PDF"
    SCANNED_PDF = "SCANNED_PDF"
    IMAGE = "IMAGE"


class ProcessingMethod(str, Enum):
    """How the raw text of a document was produced."""

    PYMUFPDF_TEXT_EXTRACTION = "PYMUFPDF_TEXT_EXTRACTION"
    PADDLE_OCR = "PADDLE_OCR"


#: Identifier stored for text extracted natively with PyMuPDF.
PYMUPDF_ENGINE: str = "pymupdf"

#: Identifier stored for text produced by the PaddleOCR engine.
PADDLE_OCR_ENGINE: str = "paddleocr"

#: Minimum total text length (characters) for a PDF to be routed as a digital
#: PDF. Below this the pages are assumed to be scans and OCR is used instead.
MIN_DIGITAL_TEXT_CHARS: int = 10

#: Resolution used when rendering scanned PDF pages for OCR input (dots per inch).
SCANNED_PDF_RENDER_DPI: int = 200

#: Per-document wall-clock budget in seconds for the whole extraction.
PROCESSING_TIMEOUT_SECONDS: float = 60.0

#: Separator inserted between the text of consecutive pages so merged output
#: keeps page boundaries visible and page order preserved.
PAGE_SEPARATOR: str = "\n\n--- Page {page_index} ---\n\n"

#: Document sources whose text must be produced by an OCR engine.
OCR_SOURCES: frozenset[DocumentSource] = frozenset(
    {DocumentSource.SCANNED_PDF, DocumentSource.IMAGE}
)

#: File formats that are processed by the module (mirrors the formats admitted
#: by technical validation).
PROCESSABLE_FORMATS: frozenset[FileFormat] = frozenset(
    {FileFormat.PDF, FileFormat.JPEG, FileFormat.PNG}
)
