"""
Specific rule implementations for different document types.
"""

from app.rules.base_rule import BaseRule
from app.schemas.document_schemas import ExtractedDocument, DocumentType
from app.schemas.verification_schemas import VerificationStatus, RuleCheckResult


class SignaturePresenceRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "GEN_001_SIGNATURE"

    @property
    def rule_name(self) -> str:
        return "Required Signature Presence"

    def evaluate(self, document: ExtractedDocument) -> RuleCheckResult:
        doc_type = document.document_type.value
        
        # Check where the signature information is stored based on document type
        sig_info = None
        if document.authority_letter:
            sig_info = document.authority_letter.signature
        elif document.account_maintenance:
            sig_info = document.account_maintenance.signature
        elif document.tripartite and document.tripartite.signatures:
            sig_info = document.tripartite.signatures[0] if document.tripartite.signatures else None
        elif document.bilateral:
            sig_info = document.bilateral.party_a_signed
        elif document.brd:
            sig_info = document.brd.signature
        elif document.request_letter:
            sig_info = document.request_letter.signature
            
        if sig_info is None:
             # Skip documents that don't strictly use this generic rule object 
             # (e.g. application form has 'all_pages_signed' boolean)
             return self.create_result(doc_type, VerificationStatus.MANUAL_REVIEW, "Signature field not parsed or N/A for this check")
             
        # Handle boolean flags directly
        if isinstance(sig_info, bool):
            is_present = sig_info
        else:
            is_present = sig_info.is_present

        if is_present:
            return self.create_result(doc_type, VerificationStatus.PASS, "Signature detected.")
        else:
            return self.create_result(doc_type, VerificationStatus.FAIL, "Required signature is missing.")


class StampPresenceRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "GEN_002_STAMP"

    @property
    def rule_name(self) -> str:
        return "Required Official Stamp Presence"

    def evaluate(self, document: ExtractedDocument) -> RuleCheckResult:
        doc_type = document.document_type.value
        
        # Find stamp info
        stamp_info = None
        doc_data = getattr(document, document.document_type.name.lower(), None)
        if hasattr(doc_data, "stamp"):
            stamp_info = doc_data.stamp
            
        if stamp_info is None:
             return self.create_result(doc_type, VerificationStatus.MANUAL_REVIEW, "Stamp field not parsed")
             
        if stamp_info.is_present:
            return self.create_result(doc_type, VerificationStatus.PASS, "Official stamp detected.")
        else:
            return self.create_result(doc_type, VerificationStatus.FAIL, "Official stamp is missing.")


class TripartiteBlankDateRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "TRI_001_BLANK_DATE"

    @property
    def rule_name(self) -> str:
        return "Preamble Date Must Be Blank"

    def evaluate(self, document: ExtractedDocument) -> RuleCheckResult:
        doc_type = document.document_type.value
        if document.document_type != DocumentType.TRIPARTITE or not document.tripartite:
            return self.create_result(doc_type, VerificationStatus.PASS, "Not a tripartite agreement.")
            
        if document.tripartite.has_preamble_date:
            return self.create_result(
                doc_type, 
                VerificationStatus.FAIL, 
                "An entered date was found in the preamble where it must remain blank.",
                field_value=document.tripartite.date_in_preamble,
                expected_value="Blank"
            )
        return self.create_result(doc_type, VerificationStatus.PASS, "Preamble date is correctly blank.")


class BilateralPlatformMentionRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "BIL_001_PLATFORM"

    @property
    def rule_name(self) -> str:
        return "Platform Terminology Check"

    def evaluate(self, document: ExtractedDocument) -> RuleCheckResult:
        doc_type = document.document_type.value
        if document.document_type != DocumentType.BILATERAL or not document.bilateral:
            return self.create_result(doc_type, VerificationStatus.PASS, "Not a bilateral agreement.")
            
        platform = document.bilateral.platform_mentioned
        valid_platforms = ["paymin", "digital muhasil", "paymere bcx"]
        
        if platform and any(vp in platform.lower() for vp in valid_platforms):
            return self.create_result(doc_type, VerificationStatus.PASS, f"Valid platform mentioned: {platform}")
        
        return self.create_result(
            doc_type, 
            VerificationStatus.FAIL, 
            "Required platform terminology (PayMin / Digital Muhasil / Paymere BCX) not found.",
            field_value=platform
        )


class EStampTextureRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "EST_001_TEXTURE"

    @property
    def rule_name(self) -> str:
        return "E-Stamp Visual Authentication"

    def evaluate(self, document: ExtractedDocument) -> RuleCheckResult:
        doc_type = document.document_type.value
        if document.document_type != DocumentType.ESTAMP or not document.estamp:
            return self.create_result(doc_type, VerificationStatus.PASS, "Not an E-Stamp.")
            
        if document.estamp.has_brownish_texture:
            return self.create_result(doc_type, VerificationStatus.PASS, "Visual texture resembles an original E-stamp.")
        elif document.estamp.has_brownish_texture is False:
            return self.create_result(doc_type, VerificationStatus.WARNING, "Document appears to be a plain white printout, not an original E-stamp texture.")
        
        return self.create_result(doc_type, VerificationStatus.MANUAL_REVIEW, "Could not automatically determine E-stamp texture.")
