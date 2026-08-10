"""
Pipeline Orchestrator.

Ties together the Preprocessor, OCR Engine, Field Extractor, and Detectors
to process an uploaded file into a structured ExtractedDocument.
"""

import os
from pathlib import Path
from typing import Union, List
from app.pipeline.preprocessor import Preprocessor
from app.pipeline.ocr_engine import OCREngine
from app.pipeline.field_extractor import FieldExtractor
from app.pipeline.stamp_signature_detector import StampSignatureDetector
from app.schemas.document_schemas import (
    ExtractedDocument, DocumentType, SignatureInfo, StampInfo, 
    BankDetails, TripartiteData, BilateralData
)


class PipelineOrchestrator:
    def __init__(self):
        self.preprocessor = Preprocessor()
        self.ocr_engine = OCREngine()
        self.field_extractor = FieldExtractor()
        self.detector = StampSignatureDetector()

    def process_document(self, file_path: Union[str, Path], doc_type: DocumentType) -> ExtractedDocument:
        """
        Run the full OCR pipeline on a document and return a structured Pydantic object.
        """
        file_path = str(file_path)
        file_name = os.path.basename(file_path)
        
        # 1. Preprocess: Extract images (handle PDF or direct Image)
        if file_path.lower().endswith('.pdf'):
            images = self.preprocessor.extract_images_from_pdf(file_path)
        else:
            import cv2
            img = cv2.imread(file_path)
            if img is None:
                raise ValueError(f"Could not read image: {file_path}")
            images = [img]
            
        if not images:
            raise ValueError("No valid images found to process.")

        # Aggregate data across pages
        full_text = ""
        is_stamp_present = False
        is_signature_present = False
        
        for img in images:
            # Enhance & Deskew
            enhanced = self.preprocessor.enhance_image_for_ocr(img)
            deskewed = self.preprocessor.deskew_image(enhanced)
            
            # OCR
            text = self.ocr_engine.extract_text(deskewed)
            full_text += text + "\n\n"
            
            # Detect Stamps & Signatures
            stamp_res = self.detector.detect_stamp(img)
            if stamp_res["is_present"]:
                is_stamp_present = True
                
            sig_res = self.detector.detect_signature(img)
            if sig_res["is_present"]:
                is_signature_present = True

        # Extract fields
        extracted_cnic = self.field_extractor.extract_cnic(full_text)
        extracted_iban = self.field_extractor.extract_iban(full_text)
        
        # Build Document object based on type
        document = ExtractedDocument(
            document_type=doc_type,
            file_name=file_name,
            raw_text=full_text,
            cnic=extracted_cnic
        )
        
        # Populate specific data structures based on type
        if doc_type == DocumentType.TRIPARTITE:
            document.tripartite = TripartiteData(
                has_preamble_date=self.field_extractor.has_keyword(full_text, "Date:"),
                bank_details=BankDetails(iban=extracted_iban) if extracted_iban else None,
                signatures=[SignatureInfo(is_present=is_signature_present)],
                stamp=StampInfo(is_present=is_stamp_present),
                raw_text=full_text
            )
        elif doc_type == DocumentType.BILATERAL:
            document.bilateral = BilateralData(
                platform_mentioned="Digital Muhasil" if self.field_extractor.has_keyword(full_text, "Digital Muhasil") else (
                    "PayMin" if self.field_extractor.has_keyword(full_text, "PayMin") else (
                        "Paymere BCX" if self.field_extractor.has_keyword(full_text, "Paymere BCX") else None
                    )
                ),
                section_6_account=BankDetails(iban=extracted_iban) if extracted_iban else None,
                party_a_signed=is_signature_present,
                stamp=StampInfo(is_present=is_stamp_present),
                raw_text=full_text
            )
        # Note: In a full production system, we'd add parsing logic for ALL 11 document types here.
        # For Phase 3 MVP, we focus on Tripartite, Bilateral, and generic attributes.
            
        return document
