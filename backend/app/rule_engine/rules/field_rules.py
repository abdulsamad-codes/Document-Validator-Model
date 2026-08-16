"""Required field presence rules.

One rule per critical field expected on the account maintenance certificate,
checking that the field carries a normalized value. A field that is entirely
absent fails the rule; a field present but not yet normalized warns, because
the pipeline state rather than the document itself is the blocker.
"""

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult

#: Category every field-presence rule belongs to.
CATEGORY = "field_presence"

#: Document types the presence rules apply to (the account maintenance
#: certificate carries the account-level identity fields).
TARGET_DOCUMENT_TYPES = frozenset({DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE})


class _FieldPresenceRule(BaseRule):
    """Base rule asserting a field has a normalized value on the AMC.

    Attributes:
        field_name: Field the rule enforces.
    """

    field_name: str

    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = [
            value
            for value in context.values(self.field_name)
            if value.document_type in {item.value for item in TARGET_DOCUMENT_TYPES}
        ]
        related_documents = sorted({value.document_id for value in values})
        related_fields = [self.field_name]
        normalized = [value for value in values if (value.normalized_value or "").strip()]
        if not values:
            return self.result(
                ValidationStatus.FAIL,
                f"Required field {self.field_name} is missing from the account "
                "maintenance certificate",
                related_document_ids=related_documents,
                related_field_names=related_fields,
            )
        if not normalized:
            return self.result(
                ValidationStatus.WARNING,
                f"Field {self.field_name} is present but has no normalized value",
                related_document_ids=related_documents,
                related_field_names=related_fields,
            )
        return self.result(
            ValidationStatus.PASS,
            f"Required field {self.field_name} is present with a normalized value",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


class FieldIbanPresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized IBAN."""

    id = "FLD_IBAN_PRESENT"
    name = "IBAN present on account maintenance certificate"
    field_name = "iban"


class FieldAccountNumberPresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized account number."""

    id = "FLD_ACCOUNT_NUMBER_PRESENT"
    name = "Account number present on account maintenance certificate"
    field_name = "account_number"


class FieldAccountHolderPresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized account holder."""

    id = "FLD_ACCOUNT_HOLDER_PRESENT"
    name = "Account holder present on account maintenance certificate"
    field_name = "account_holder"


class FieldBankNamePresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized bank name."""

    id = "FLD_BANK_NAME_PRESENT"
    name = "Bank name present on account maintenance certificate"
    field_name = "bank_name"


__all__ = [
    "FieldIbanPresenceRule",
    "FieldAccountNumberPresenceRule",
    "FieldAccountHolderPresenceRule",
    "FieldBankNamePresenceRule",
]
