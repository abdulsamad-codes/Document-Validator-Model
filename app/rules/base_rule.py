"""
Base interfaces for the Business Rule Engine.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Any
from app.schemas.verification_schemas import RuleCheckResult, VerificationStatus
from app.schemas.document_schemas import ExtractedDocument

class BaseRule(ABC):
    """Abstract base class for all business rules."""
    
    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for the rule."""
        pass
        
    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Human-readable name of the rule."""
        pass

    def create_result(self, document_type: str, status: VerificationStatus, 
                      message: str, field_value: Optional[str] = None, 
                      expected_value: Optional[str] = None) -> RuleCheckResult:
        """Helper to construct a RuleCheckResult."""
        return RuleCheckResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            document_type=document_type,
            status=status,
            message=message,
            field_value=field_value,
            expected_value=expected_value
        )

    @abstractmethod
    def evaluate(self, document: ExtractedDocument) -> RuleCheckResult:
        """Evaluate the rule against the extracted document data."""
        pass
