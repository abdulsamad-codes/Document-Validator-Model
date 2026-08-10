"""
Core Business Rule Engine for the Financial Document Verification System.
"""

from typing import List, Dict, Optional
from app.schemas.document_schemas import ExtractedDocument, DocumentType
from app.schemas.verification_schemas import (
    VerificationReport, 
    DocumentVerificationResult, 
    CrossDocumentMatch, 
    VerificationStatus
)
from app.rules.base_rule import BaseRule
from app.rules.document_rules import (
    SignaturePresenceRule,
    StampPresenceRule,
    TripartiteBlankDateRule,
    BilateralPlatformMentionRule,
    EStampTextureRule
)
from config import EXACT_MATCH_FIELDS


class RuleEngine:
    def __init__(self):
        # Register standard rules
        self.general_rules = [
            SignaturePresenceRule(),
            StampPresenceRule()
        ]
        
        # Map document types to their specific rules
        self.doc_specific_rules = {
            DocumentType.TRIPARTITE: [TripartiteBlankDateRule()],
            DocumentType.BILATERAL: [BilateralPlatformMentionRule()],
            DocumentType.ESTAMP: [EStampTextureRule()]
        }

    def verify_document(self, document: ExtractedDocument) -> DocumentVerificationResult:
        """Run all applicable rules on a single document."""
        result = DocumentVerificationResult(
            document_type=document.document_type.value,
            file_name=document.file_name
        )
        
        rules_to_run: List[BaseRule] = self.general_rules.copy()
        if document.document_type in self.doc_specific_rules:
            rules_to_run.extend(self.doc_specific_rules[document.document_type])
            
        for rule in rules_to_run:
            rule_result = rule.evaluate(document)
            result.rule_results.append(rule_result)
            
            # Update counts
            if rule_result.status == VerificationStatus.PASS:
                result.pass_count += 1
            elif rule_result.status == VerificationStatus.FAIL:
                result.fail_count += 1
            elif rule_result.status == VerificationStatus.WARNING:
                result.warning_count += 1
            elif rule_result.status == VerificationStatus.MANUAL_REVIEW:
                result.manual_review_count += 1
                
        # Determine overall document status
        if result.fail_count > 0:
            result.overall_status = VerificationStatus.FAIL
        elif result.manual_review_count > 0:
            result.overall_status = VerificationStatus.MANUAL_REVIEW
        elif result.warning_count > 0:
            result.overall_status = VerificationStatus.WARNING
        else:
            result.overall_status = VerificationStatus.PASS
            
        return result

    def _cross_check_field(self, field_name: str, docs: List[ExtractedDocument], extract_func) -> Optional[CrossDocumentMatch]:
        """Helper to cross-check a specific field across multiple documents."""
        values = {}
        for doc in docs:
            val = extract_func(doc)
            if val is not None:
                values[doc.document_type.value] = val
                
        if len(values) < 2:
            return None # Not enough documents to cross-compare
            
        # Check consistency
        first_val = list(values.values())[0]
        # Exact match required for banking/ID fields
        is_consistent = all(v == first_val for v in values.values())
        
        status = VerificationStatus.PASS if is_consistent else VerificationStatus.FAIL
        msg = f"{field_name} matches across documents." if is_consistent else f"{field_name} mismatch detected."
        
        return CrossDocumentMatch(
            field_name=field_name,
            documents_compared=list(values.keys()),
            values_found=values,
            is_consistent=is_consistent,
            status=status,
            message=msg
        )

    def perform_cross_document_checks(self, documents: List[ExtractedDocument]) -> List[CrossDocumentMatch]:
        """Cross-verifies consistency of IBAN, Account Numbers, and Org Names."""
        cross_checks = []
        
        # 1. Check Account Number Consistency (Maintenance, Tripartite, Bilateral)
        def get_acc_num(doc):
            if doc.account_maintenance and doc.account_maintenance.bank_details:
                return doc.account_maintenance.bank_details.account_number
            if doc.tripartite and doc.tripartite.bank_details:
                return doc.tripartite.bank_details.account_number
            if doc.bilateral and doc.bilateral.section_6_account:
                return doc.bilateral.section_6_account.account_number
            return None
            
        acc_check = self._cross_check_field("account_number", documents, get_acc_num)
        if acc_check:
            cross_checks.append(acc_check)
            
        # 2. Check IBAN Consistency
        def get_iban(doc):
            if doc.account_maintenance and doc.account_maintenance.bank_details:
                return doc.account_maintenance.bank_details.iban
            if doc.tripartite and doc.tripartite.bank_details:
                return doc.tripartite.bank_details.iban
            if doc.bilateral and doc.bilateral.section_6_account:
                return doc.bilateral.section_6_account.iban
            return None
            
        iban_check = self._cross_check_field("iban", documents, get_iban)
        if iban_check:
            cross_checks.append(iban_check)
            
        return cross_checks

    def generate_verification_report(self, case_id: str, documents: List[ExtractedDocument]) -> VerificationReport:
        """Runs the complete verification pipeline and returns the final report."""
        report = VerificationReport(case_id=case_id)
        
        # 1. Verify each document individually
        for doc in documents:
            doc_result = self.verify_document(doc)
            report.document_results.append(doc_result)
            
            report.total_rules_checked += len(doc_result.rule_results)
            report.total_pass += doc_result.pass_count
            report.total_fail += doc_result.fail_count
            report.total_warnings += doc_result.warning_count
            report.total_manual_review += doc_result.manual_review_count
            
        # 2. Perform cross-document verification
        cross_checks = self.perform_cross_document_checks(documents)
        for check in cross_checks:
            report.cross_document_checks.append(check)
            report.total_rules_checked += 1
            if check.status == VerificationStatus.PASS:
                report.total_pass += 1
            else:
                report.total_fail += 1
                
        # 3. Determine overall application status
        if report.total_fail > 0:
            report.overall_status = VerificationStatus.FAIL
        elif report.total_manual_review > 0:
            report.overall_status = VerificationStatus.MANUAL_REVIEW
        elif report.total_warnings > 0:
            report.overall_status = VerificationStatus.WARNING
        else:
            report.overall_status = VerificationStatus.PASS
            
        return report
