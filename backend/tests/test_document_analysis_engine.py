"""Unit tests for the document analysis engine.

Covers document type detection, per-type field extraction, the reusable
validators, the cross-field consistency rules, the deterministic scoring and the
analysis repository. All fixtures are pure text, so no OCR engine or database
is needed except where explicitly noted.
"""

import pytest

from app.database.connection import SessionLocal
from app.database.models.enums import ApplicationStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.document_analysis.constants import (
    AnalyzedDocumentType,
    VerificationStatus,
)
from app.document_analysis.exceptions import UnsupportedDocumentType
from app.document_analysis.extractors import (
    _parse_amount,
    detect_document_type,
    extract_fields,
)
from app.document_analysis.schemas import AnalysisOutcome
from app.document_analysis.services import DocumentAnalysisService
from app.document_analysis.rules import (
    RulesEngine,
    compute_score,
    compute_verification_status,
    scoring_components,
)
from app.document_analysis.validators import (
    ValidatorEngine,
    validate_account_number,
    validate_currency,
    validate_date,
    validate_date_not_future,
    validate_iban,
    validate_salary_month,
)

BANK_STATEMENT_TEXT = """MONTHLY ACCOUNT STATEMENT
Account Holder: John A. Doe
Account Number: 1234567890
IBAN: DE89370400440532013000
Bank: Sparkasse
Statement Period: 01/01/2026 - 31/01/2026
Opening Balance: 1,250.50
Closing Balance: 3,200.75
Total Credits: 2,500.00
Total Debits: 549.75
Currency: EUR
Transactions: 23
"""

PAYSLIP_TEXT = """PAYSLIP
Employee Name: Jane Q. Roe
Employee ID: EMP-1001
Employer Name: Acme Corp GmbH
Gross Salary: 5,000.00
Net Salary: 3,850.50
Salary Month: 2026-01
Payment Date: 2026-01-31
"""

ID_TEXT = """NATIONAL IDENTITY CARD
Full Name: Jose P. Garcia
Date of Birth: 1990-05-15
ID Number: 1234567890
Nationality: Spain
Issue Date: 2018-06-01
Expiry Date: 2028-06-01
"""

TAX_TEXT = """TAX RETURN SUMMARY
Taxpayer Name: Maria K. Novak
Tax Reference Number: TAX-2025-000123
Tax Year: 2025
Gross Income: 45,000.00
Total Tax: 9,800.00
Currency: EUR
"""

#: Synthetic (fabricated, non-real) fixture mirroring the structural pattern
#: docs/Master_Rules_Combined.md Section 7 describes for a Bilateral
#: Agreement -- department name, PayMin/Digital Muhasil/Paymere BCX platform
#: terminology, a Section 5.2 PKR transaction-charge line and a Section 6
#: account block. Never real extracted values.
BILATERAL_AGREEMENT_TEXT = """BILATERAL AGREEMENT
This Agreement is made between the Bank and the Department.
Department: Sample Regional Development Authority

Section 5 - Transaction Charges
Section 5.2: As per prevailing charges of 1-Link, PKR 15 per transaction, payable via PayMin.

Section 6 - Account Information
Account Title: Sample Regional Development Authority
Account Number: 9876543210
IBAN: DE89370400440532013000
Effective Date: 2026-01-15
"""

#: Synthetic (fabricated, non-real) fixtures mirroring the real prose-embedded
#: Authority Letter template confirmed on two independent real departments in
#: Confidential Data/ -- structurally near-identical wording, one using a
#: comma before the designation, the other parenthesizing it. Never real
#: extracted values.
AUTHORITY_LETTER_TEXT_COMMA_FORM = """AUTHORITY LETTER
It is hereby authorized that Mr. Naveed Khan, Deputy Director Administration \
(BPS-18) is authorized to deal with and conduct correspondence and matter \
related to 1-Link and the Khyber Pakhtunkhwa Information Technology Board \
(KPITB) on the behalf of Directorate.
"""

AUTHORITY_LETTER_TEXT_PAREN_FORM = """AUTHORITY LETTER
It is hereby authorized that Mr. Salman Raza (Assistant Finance Officer) \
Tehsil Municipal Administration Sample is authorized to deal with and \
conduct correspondence and matters related to 1-Link and the Khyber \
Pakhtunkhwa Information Technology Board (KPITB) on behalf of TMA Sample \
District.
"""

ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT = """FUTURE BANK LIMITED
ACCOUNT MAINTENANCE CERTIFICATE

This is to certify that the following account is maintained with us:

Account Title: KHYBER PROVINCE UTILITIES BOARD
Account Number: 01234567890123
IBAN: PK36FUTB0000001123456702
Bank Name: Future Bank Limited
Branch Name: Main Branch, Peshawar
Date of Issue: 15/08/2026
"""

TRIPARTITE_AGREEMENT_TEXT = """TRIPARTITE AGREEMENT
This Tripartite Agreement is made and entered into by and between:
1-Link (Private) Limited, having its registered office at 4th Floor, State Life Building, Karachi (hereinafter referred to as '1-Link')
Khyber Pakhtunkhwa Information Technology Board, having its registered office at Civil Secretariat, Peshawar (hereinafter referred to as 'KPITB')
Transport and Mass Transit Department, Government of Khyber Pakhtunkhwa, having its office at Peshawar (hereinafter referred to as the 'Sub-biller')

Bank Details:
Account Title: KHYBER PROVINCE UTILITIES BOARD
Account Number: 01234567890123
Branch: Main Branch, Peshawar
"""

#: Synthetic (fabricated, non-real) fixtures mirroring the three real BRD
#: structural variants confirmed in Confidential Data/ (three independent
#: departments) -- unlike Authority Letter, no shared template exists, so
#: each fixture mirrors a different real department's actual shape rather
#: than one clean case. Never real extracted values.
BRD_TEXT_PROSE_FORM = """BUSINESS REQUIREMENT DOCUMENT
The Directorate of Sample Affairs, Sample Province, was established in 1995
and provides recreational facilities across the region. Visitors register
for membership and pay the prescribed fees at each facility office.
For ease and transparency, this office is already collaborating with KPITB
on a Management Information System and plans to integrate digital payment
solutions through KPITB's FinTech Unit within the system.
"""

BRD_TEXT_NUMBERED_LIST_FORM = """BUSINESS REQUIREMENT DOCUMENTS
Tehsil Municipal Administration Sample is a local government entity
responsible for providing Municipal Services to the general public. The
major sources of Income of this TMA are:
1. General Bus Stand
2. Cattle Fair Sample
3. Service Fee
INTENTION TO ON-BOARD DEPARTMENT FOR THE ENABLEMENT OF THE DIGITAL
PAYMENTS VIA KPITB's FIN TECH UNIT
This Office intends to go towards Digital Payments via KPITB'S FIN TECH
UNIT.
"""

BRD_TEXT_CATEGORIZED_BULLETS_FORM = """Business Requirement Document
1. Brief Background of Department:
The Sample Development Authority is a government organization responsible
for planning and development in the Sample region.
2. SERVICES OFFERED:
Revenue Collection
Taxes (Property Tax, Water Tax)
Miscellaneous (Registration Fee, Lease Renewal, Rents)
4. Intention to on-board department for the enablement of the digital
payments via KPITB's FinTech Unit
The Authority intends to collaborate with KPITB's FinTech Unit to digitize
all revenue streams.
"""

#: Missing the digitization-intent confirmation entirely -- a real BRD would
#: never omit this per docs/Master_Rules_Combined.md Section 10, but the
#: extractor must still degrade honestly (missing, not invalid) rather than
#: raise.
BRD_TEXT_NO_DIGITIZATION_MENTION = """BUSINESS REQUIREMENT DOCUMENT
The Directorate of Sample Affairs was established in 1995 and provides
recreational facilities across the region. Visitors pay the prescribed
fees at each facility office.
"""

#: Missing the services-list mention -- unlike the digitization-intent case
#: above, this field is non-critical, but Section 10 still requires it, so
#: its absence must stay visible to a human reviewer (a "missing" validation
#: result and a downgraded, non-VERIFIED status) rather than being hidden by
#: the non-critical classification.
BRD_TEXT_NO_SERVICES_MENTION = """BUSINESS REQUIREMENT DOCUMENT
The Directorate of Sample Affairs, Sample Province, was established in 1995
and provides recreational facilities across the region.
For ease and transparency, this office is already collaborating with KPITB
on a Management Information System and plans to integrate digital payment
solutions through KPITB's FinTech Unit within the system.
"""


#: Synthetic (fabricated, non-real) fixture mirroring the real single-account
#: clause-(v)/clause-(x) shape found in one of the two real organizations
#: (Confidential Data/.ocr_cache/TMA_Khal_Dir_Lower__ONE_LINK_LETTER_copy1.txt):
#: one specific account stated in one sentence, with an unambiguous branch code
#: in a nested parenthetical. Never real extracted values.
ONE_LINK_LETTER_TEXT_SINGLE_ACCOUNT = """PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS
(v)
hereby authorize 1LINK for each transaction to carry out settlement and clearing functions as per
Operating Guidelines, in the bank account number (IBAN) PK00SAMP0000000000000000 titled as Sample General Account
SAMPLE TEHSIL MUNICIPAL ADMINISTRATION maintained with (SAMPLE BANK) in its
branch (Sample Road Branch (0099)):
(x)
shall ensure business continuity planning (BCP) and disaster recovery (DR) at their side. SAMPLE
TEHSIL MUNICIPAL ADMINISTRATION hereby authorizes 1LINK to take actions, as it deems
necessary, to ensure BCP, DR, business operations and network connectivity and SAMPLE
TEHSIL MUNICIPAL ADMINISTRATION will accept such measures.
"""

#: Synthetic (fabricated, non-real) fixture mirroring the real multi-bank
#: reference-table shape found in the other real organization (Confidential
#: Data/.ocr_cache/GDA_Abbotabad__ONE_LINK_LETTER_copy1-3.txt): organization
#: name is still present via clause (x), but clause (v)'s bank details are a
#: table of several banks with no textual indication of which is operative --
#: branch_code must come back missing here, not a guessed row. Never real
#: extracted values.
ONE_LINK_LETTER_TEXT_MULTI_BANK_TABLE = """PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS
(x)
shall ensure business continuity planning (BCP) and disaster recovery (DR) at their side. SAMPLE
DEVELOPMENT AUTHORITY hereby authorizes 1LINK to take actions, as it deems
necessary, to ensure BCP, DR, business operations and network connectivity and SAMPLE
DEVELOPMENT AUTHORITY accept such measures.
(v)
Agreement or as communicated through 1LINK Schedule of Charges from time to time, in the
FOLLOWING bank accounts:
Sr No. Bank Name Account No
1. Sample Bank One
Sample Branch
PK00 SAMP 0000 0000 0000 0000
2. Sample Bank Two
Sample Road Branch (0099)
PK00 SAMB 0000 0000 0000 0001
"""

#: Missing the organization-name clause entirely -- organization_name is
#: critical for this type, so its absence must force manual review rather
#: than a silent pass.
ONE_LINK_LETTER_TEXT_NO_ORG_NAME = """PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS
(v)
hereby authorize 1LINK for each transaction to carry out settlement and clearing functions.
(vi)
for each Transaction carried out by the Sub-Billers/Bill Aggregator Member, shall abide by the
Operating Guidelines.
"""


#: Synthetic (fabricated, non-real), mirroring the clean label-then-value
#: layout confirmed in 2 of 3 real cached samples (Confidential Data/.ocr_cache/,
#: DG_Sports_KP_Onboarding_Documents__CNIC_FRONT_copy1/2.txt): each label sits
#: on its own line, immediately followed by its value -- single labels get a
#: single value line, adjacent label pairs get a matching value-pair.
CNIC_FRONT_TEXT_CLEAN = """PAKISTAN
National Identity Card
ISLAMIC REPUBLIC OF PAKISTAN
Name
Samia Naz
Father Name
Nasir Mehmood
Gender
Country of Stay
F
Pakistan
Identity Number
Date of Birth
12345-1234567-1
01.01.1990
Date of Issue
Date of Expiry
01.01.2020
01.01.2030
Holder's Signature
12345-1234567-1
Registrar General of Pakistan
"""

#: Synthetic (fabricated, non-real), mirroring the scrambled read-order
#: confirmed in the third real cached sample (copy3.txt): labels and values
#: are interleaved out of order except for the "Name" label, which -- by the
#: same coincidence seen in the real sample -- still sits directly before its
#: value. document_number and full_name must still extract; date_of_expiry's
#: two-label/two-value block never occurs intact, so it must honestly miss.
CNIC_FRONT_TEXT_SCRAMBLED = """76494
ISLAMIC REPUBLIC OF PAKISTAN
PAKISTAN
Date of Issue
Identity Number
GenderCountry of Stay
01.01.2020
12345-1234567-1
Father Name
F
Name
Samia Naz
Nasir Mehmood
Pakistan
Date of Expiry
Date of Birth
National Identity Card
01.01.1990
Holder's Signature
"""

#: Missing only the "Name" clause -- document_number and date_of_expiry both
#: still extract, so this isolates full_name's absence from the other two
#: expected fields (unlike a text missing everything, which would drag the
#: score down for unrelated reasons and force review regardless of full_name).
CNIC_FRONT_TEXT_NO_NAME = """PAKISTAN
National Identity Card
ISLAMIC REPUBLIC OF PAKISTAN
Identity Number
Date of Birth
12345-1234567-1
01.01.1990
Date of Issue
Date of Expiry
01.01.2020
01.01.2030
Holder's Signature
"""


def _components(text: str):
    document_type = detect_document_type(text)
    fields = extract_fields(text, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    consistency = RulesEngine().run(document_type, fields)
    return document_type, fields, validations, consistency


# --- Document type detection -------------------------------------------------


def test_detect_bank_statement():
    assert detect_document_type(BANK_STATEMENT_TEXT) is AnalyzedDocumentType.BANK_STATEMENT


def test_detect_payslip():
    assert detect_document_type(PAYSLIP_TEXT) is AnalyzedDocumentType.PAYSLIP


def test_detect_identity_document():
    assert detect_document_type(ID_TEXT) is AnalyzedDocumentType.ID_DOCUMENT


def test_detect_tax_document():
    assert detect_document_type(TAX_TEXT) is AnalyzedDocumentType.TAX_DOCUMENT


def test_detect_unknown_document():
    text = "This is a casual letter with no financial keywords whatsoever."
    assert detect_document_type(text) is AnalyzedDocumentType.UNKNOWN


def test_detection_is_case_insensitive():
    assert detect_document_type(BANK_STATEMENT_TEXT.lower()) is AnalyzedDocumentType.BANK_STATEMENT


# --- Field extraction --------------------------------------------------------


def test_extract_bank_statement_fields():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    assert fields["account_holder"] == "John A. Doe"
    assert fields["account_number"] == "1234567890"
    assert fields["iban"] == "DE89370400440532013000"
    assert fields["bank_name"] == "Sparkasse"
    assert fields["statement_period"] == {"start": "2026-01-01", "end": "2026-01-31"}
    assert fields["opening_balance"] == 1250.5
    assert fields["closing_balance"] == 3200.75
    assert fields["total_credits"] == 2500.0
    assert fields["total_debits"] == 549.75
    assert fields["currency"] == "EUR"
    assert fields["transaction_count"] == 23


def test_extract_payslip_fields():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    assert fields["employee_name"] == "Jane Q. Roe"
    assert fields["employee_id"] == "EMP-1001"
    assert fields["employer_name"] == "Acme Corp GmbH"
    assert fields["gross_salary"] == 5000.0
    assert fields["net_salary"] == 3850.5
    assert fields["salary_month"] == "2026-01"
    assert fields["payment_date"] == "2026-01-31"


def test_extract_identity_fields():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    assert fields["full_name"] == "Jose P. Garcia"
    assert fields["date_of_birth"] == "1990-05-15"
    assert fields["document_number"] == "1234567890"
    assert fields["nationality"] == "Spain"
    assert fields["issue_date"] == "2018-06-01"
    assert fields["expiry_date"] == "2028-06-01"


def test_extract_tax_fields():
    fields = extract_fields(TAX_TEXT, AnalyzedDocumentType.TAX_DOCUMENT)
    assert fields["taxpayer_name"] == "Maria K. Novak"
    assert fields["tax_reference_number"] == "TAX-2025-000123"
    assert fields["tax_year"] == 2025
    assert fields["gross_income"] == 45000.0
    assert fields["total_tax"] == 9800.0
    assert fields["currency"] == "EUR"


def test_extract_unknown_type_raises():
    with pytest.raises(UnsupportedDocumentType):
        extract_fields("some text", AnalyzedDocumentType.UNKNOWN)


def test_extract_bilateral_agreement_fields():
    fields = extract_fields(
        BILATERAL_AGREEMENT_TEXT, AnalyzedDocumentType.BILATERAL_AGREEMENT
    )
    assert fields["organization_name"] == "Sample Regional Development Authority"
    assert fields["platform_name"] == "PayMin"
    assert "PKR 15 per transaction" in fields["transaction_charges"]
    assert fields["account_holder"] == "Sample Regional Development Authority"
    assert fields["account_number"] == "9876543210"
    assert fields["iban"] == "DE89370400440532013000"
    assert fields["effective_date"] == "2026-01-15"


def test_bilateral_agreement_validators_and_scoring():
    document_type = AnalyzedDocumentType.BILATERAL_AGREEMENT
    fields = extract_fields(BILATERAL_AGREEMENT_TEXT, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["account_number"]["status"] == "valid"
    assert by_field["iban"]["status"] == "valid"
    assert by_field["effective_date"]["status"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_authority_letter_fields_comma_form():
    fields = extract_fields(
        AUTHORITY_LETTER_TEXT_COMMA_FORM, AnalyzedDocumentType.AUTHORITY_LETTER
    )
    assert fields["focal_person_name"] == "Naveed Khan"
    assert fields["focal_person_designation"] == "Deputy Director Administration"
    assert fields["organization_name"] == "Directorate"


def test_extract_authority_letter_fields_paren_form():
    fields = extract_fields(
        AUTHORITY_LETTER_TEXT_PAREN_FORM, AnalyzedDocumentType.AUTHORITY_LETTER
    )
    assert fields["focal_person_name"] == "Salman Raza"
    assert fields["focal_person_designation"] == "Assistant Finance Officer"
    assert fields["organization_name"] == "TMA Sample District"


def test_authority_letter_validators_and_scoring():
    document_type = AnalyzedDocumentType.AUTHORITY_LETTER
    fields = extract_fields(AUTHORITY_LETTER_TEXT_COMMA_FORM, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    # No account fields in this real-shaped fixture -- must be reported
    # missing, not invalid, and must not force a critical failure (they are
    # deliberately not critical fields for this type).
    assert by_field["account_number"]["status"] == "missing"
    assert by_field["iban"]["status"] == "missing"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_account_maintenance_certificate_fields():
    fields = extract_fields(
        ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
    assert fields["account_number"] == "01234567890123"
    assert fields["iban"] == "PK36FUTB0000001123456702"
    assert fields["bank_name"] == "Future Bank Limited"
    assert fields["branch_name"] == "Main Branch, Peshawar"
    assert fields["issue_date"] == "2026-08-15"


def test_extract_tripartite_agreement_fields():
    fields = extract_fields(
        TRIPARTITE_AGREEMENT_TEXT,
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    assert fields["party_1link"] == "1-Link (Private) Limited"
    assert fields["party_kpitb"] == "Khyber Pakhtunkhwa Information Technology Board"
    assert "Transport and Mass Transit Department" in fields["party_subbiller"]
    assert fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
    assert fields["account_number"] == "01234567890123"
    assert fields["branch_code"] == "Main Branch, Peshawar"


#: Synthetic fixture mirroring the compound-document table layout found in
#: TMA Thall Agreement.docx (2026-08-20): the Tripartite section appears as a
#: signature table (parties listed in columns) followed by an account/fee table,
#: with no labeled "Account Number: <value>" block -- the account number sits in
#: the last column of a "Sr No | Bank Name | Account No" table row instead.
#: Fabricated data (PK99FAKE IBAN) -- never real extracted values.
TRIPARTITE_AGREEMENT_COMPOUND_TABLE_TEXT = """\
1. | For & Behalf of | 2 | For & Behalf of | 3 | For & Behalf of
1 LINK (Pvt) Limited | Fake Municipal Administration | Khyber Pakhtunkhwa Information & Technology Board (KP-ITB)
Name:
Designation:
CNIC: | Name:
Designation:
CNIC: | Name:
Designation:

Amount in PKR (Transaction Range) | Transaction Charges (Including 1-LINK)
PKR 1-10,000 | PKR 25.00 per transaction

Sr No | Bank Name | Account No
01 | Bank of Fake Branch | PK99FAKE00012345678901
"""


def test_extract_tripartite_agreement_compound_table_layout():
    """account_number must be extracted from a pipe-separated table row (not a
    labeled-block). Validated on n=1 real sample (TMA Thall Agreement.docx,
    2026-08-20) -- an unusually messy compound doc, not a clean split page.
    The party_1link fix (spaced '1 LINK') and party_kpitb fix (optional '&')
    are also exercised here.
    """
    fields = extract_fields(
        TRIPARTITE_AGREEMENT_COMPOUND_TABLE_TEXT,
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    # 1 LINK (with space) must now be recognised
    assert "1 LINK" in fields.get("party_1link", ""), (
        f"party_1link should contain '1 LINK'; got {fields.get('party_1link')!r}"
    )
    # KPITB with & variant must now be recognised
    assert (
        "Khyber Pakhtunkhwa Information" in fields.get("party_kpitb", "")
        or fields.get("party_kpitb") == "KP-ITB"
    ), f"party_kpitb not extracted; got {fields.get('party_kpitb')!r}"
    # Table-row account number (PK99FAKE...) must be extracted
    assert fields.get("account_number") == "PK99FAKE00012345678901", (
        f"account_number: expected 'PK99FAKE00012345678901'; got {fields.get('account_number')!r}"
    )

#: Synthetic (fabricated, non-real) fixtures for the structural bank-account
#: block parser, mirroring the real OCR layouts confirmed in Confidential Data/
#: (see the extractor docstrings). Every account number / IBAN / CNIC below is
#: invented; the "PK99FAKE..." IBAN shape keeps the values unambiguously fake.
#: The column-table shape comes from TMA Lal Dir Upper (header block mapped
#: positionally onto the value block, with an OCR-noise header line), the
#: interleaved/dotted-leader/wrapped shapes from the four GDA Abbotabad AMC
#: copies (Allied, ZTBL, NBP, BOK).
TRIPARTITE_COLUMN_TABLE_TEXT = """TRIPARTITE AGREEMENT
This Tripartite Agreement is made and entered into by and between:
1-Link (Private) Limited, ... (hereinafter referred to as '1-Link')
Bank details shall be maintained as follows:
S#
Bank Name
IENT
Account Title
IBAN/Account No
01
Sample Bank Branch
Sample Regional Development Authority
PK99FAKE0000000000000000
Branch (0312)
"""

DOTTED_LEADER_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
ACCOUNT NUMBER:... 00112233445566
Title of AccOunt: SAMPLE DEVELOPMENT AUTHORITY.
IBAN:PK99FAKE0000000000000000...
"""

COMBINED_VALUE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the following account is maintained with us:
Title of Account
SAMPLE AUTHORITY
Account No/IBAN
00112233445566/PK99FAKE0000000000000000
Date of Account Opening
01 JANUARY 2000
"""

WRAPPED_TITLE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
TITLE OF ACCOUNT
SAMPLE AUTHORITY (SAMPLE REGIONAL
DEVELOPMENT
FUND)
CNIC OF AUTHORIZED SIGNATORY
12345-1234567-1
ACCOUNT NO
1234567890
ACCOUNT NO/IBAN
PK99FAKE0000000000000000
"""

FIRST_MATCH_WINS_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
ACCOUNT NUMBER:... 00112233445566
Title of AccOunt: FIRST PAGE AUTHORITY.
IBAN:PK99FAKE0000000000000000...
--- page break ---
Account Title
SECOND PAGE AUTHORITY
Account NO.
PK88FAKE0000000000000000
"""

ROW_INDEX_GUARD_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account Title
Sample Authority
Account No
01
Account Status
Active
"""

PARTIAL_CERT_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account Title: SAMPLE AUTHORITY
"""

PARENTHETICAL_LABEL_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Title of Account
SAMPLE AUTHORITY
Account No. (T-24 System)
00112233445566
IBAN: PK99FAKE0000000000000000
"""

PARENTHETICAL_LABEL_INLINE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account Title: SAMPLE AUTHORITY
Account No. (T-24 System): 00112233445566
"""

PAREN_IBAN_INLINE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account No.: PK99FAKE0000000000000000
"""

PARALLEL_GENERATIONS_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the account of SAMPLE SPORTS AUTHORITY maintained
with this branch is in good standing.
Account No. (T-24 System)
00112233445566
Account No. (CBS)
00112233445567
Account No. (Core Banking)
00112233445568
"""

SENTENCE_NO_OWNERSHIP_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the following account is maintained with us.
Account No.
00112233445566
"""

PAREN_IBAN_OCR_NOISE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the following account is maintained with us.
account number (1BAN) PK99FAKE0000000000000000 titled as Tehsil General Account
Account Title
SAMPLE AUTHORITY
"""

SUBJECT_VERB_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
It is certified that SAMPLE SPORTS AUTHORITY maintaining account with SAMPLE
BANK Mandian Branch (1234) as per below mentioned details.
ACCOUNT NO
00112233445566
"""

SUBJECT_VERB_IS_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that SAMPLE SPORTS AUTHORITY is maintaining a current
account with our bank.
ACCOUNT NO
00112233445566
"""

SUBJECT_VERB_TITLE_CASE_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that Sample Sports Complex is maintaining a current account
at The Bank of Khyber since 01-01-2000. Following are the account details:
ACCOUNT NO
00112233445566
"""

WE_ARE_MAINTAINING_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
We are maintaining the above mentioned account in our branch.
ACCOUNT NO
00112233445566
"""

BALANCED_PAREN_TITLE_STOP_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
TITLE OF ACCOUNT
SAMPLE SPORTS (SAMPLE DEVELOPMENT
AUTHORITY)
SAMPLE FUND
CNIC OF AUTHORIZED SIGNATORY
12345-1234567-1
ACCOUNT NO
1234567890
"""

PREFIXED_GENERATIONS_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that SAMPLE SPORTS COMPLEX is maintaining a BOK Saving Account at The Bank of
Khyber, Main Corporate Branch Peshawar. Following are the account details:
Old Account No (U-Bank Plus)
00112233445560
Old IBAN No. (U-Bank Plus)
PK99FAKE0100010200000001
Account No. (T-24 System)
00112233445561
IBAN No. (T-24 System)
PK99FAKE0200010000000001
New Account No. (T-24 Islamic)
00112233445562
New IBAN No. (T-24 Islamic)
PK99FAKE0300010000000001
"""

OLD_PREFIX_BEFORE_ANCHORED_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that SAMPLE SPORTS COMPLEX is maintaining a BOK Saving Account at The Bank of
Khyber, Main Corporate Branch Peshawar. Following are the account details:
Old Account No (U-Bank Plus)
00112233445560
Account No. (T-24 System)
00112233445561
IBAN No. (T-24 System)
PK99FAKE0200010000000001
"""


def test_extract_tripartite_column_table_positions_values_by_header():
    # The real Tripartite layout is a stacked column table whose header block
    # ("S# / Bank Name / IENT / Account Title / IBAN/Account No") maps
    # positionally onto the value block. The OCR-noise "IENT" header must not
    # shift the mapping, the row index "01" must not become the account number,
    # and the IBAN-only value in the account slot must be promoted to
    # account_number (Tripartite has no separate iban field).
    fields = extract_fields(
        TRIPARTITE_COLUMN_TABLE_TEXT,
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    assert fields["account_holder"] == "Sample Regional Development Authority"
    assert fields["account_number"] == "PK99FAKE0000000000000000"
    assert "iban" not in fields


def test_extract_dotted_leader_same_line_values():
    # ZTBL's AMC uses "Label:... value" dotted leaders; trailing separator dots
    # on the IBAN value are OCR noise and must be stripped.
    fields = extract_fields(
        DOTTED_LEADER_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE DEVELOPMENT AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_combined_account_number_iban_value():
    # Allied's AMC lists "Account No/IBAN" with a combined "<number>/<IBAN>"
    # value that must be split into the two fields.
    fields = extract_fields(
        COMBINED_VALUE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_wrapped_multiline_account_title():
    # NBP's AMC wraps the account title across three OCR lines; capture must
    # join them and stop before the next field's label ("CNIC OF AUTHORIZED
    # SIGNATORY"), while the later IBAN-only "ACCOUNT NO/IBAN" value must feed
    # the iban field, not overwrite the plain account number.
    fields = extract_fields(
        WRAPPED_TITLE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == (
        "SAMPLE AUTHORITY (SAMPLE REGIONAL DEVELOPMENT FUND)"
    )
    assert fields["account_number"] == "1234567890"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_first_page_value_wins_over_later_page():
    # ZTBL's page 1 and NRSP's page 2 both state account details for the same
    # document; the page-1 values must win (first match in document order), so
    # the account number is never the page-2 IBAN-shaped value.
    fields = extract_fields(
        FIRST_MATCH_WINS_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "FIRST PAGE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_row_index_never_becomes_account_number():
    # An all-digit value of length <= 3 (a table row index / page marker) must
    # never be captured as the account number -- the shape guard rejects it,
    # which generalizes across row indices 01/02/03 rather than blacklisting a
    # specific value.
    fields = extract_fields(
        ROW_INDEX_GUARD_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "Sample Authority"
    assert "account_number" not in fields
    assert "iban" not in fields


def test_extract_partial_certificate_missing_fields_are_absent():
    # A certificate that genuinely carries no account number must report the
    # field as absent rather than fabricate one.
    fields = extract_fields(
        PARTIAL_CERT_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert "account_number" not in fields
    assert "iban" not in fields


def test_extract_parenthetical_label_value_on_next_line():
    # The real DG_Sports AMC labels its account number "Account No. (T-24
    # System)" -- a parenthetical naming the bank system. The qualifier must be
    # consumed into the label (not mistaken for an inline value) so the number
    # on the following line is captured.
    fields = extract_fields(
        PARENTHETICAL_LABEL_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_parenthetical_label_inline_value_after_colon():
    # The same qualifier shape with the value on the same line after a colon
    # must also extract, and a parenthetical IBAN value must never be eaten by
    # the qualifier-stripping rule.
    fields = extract_fields(
        PARENTHETICAL_LABEL_INLINE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    fields = extract_fields(
        PAREN_IBAN_INLINE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_first_of_parallel_account_generations():
    # The real DG_Sports AMC certifies the account under three parallel bank
    # systems (T-24, CBS, Core), each its own labeled block, and states the
    # holder only in prose -- never as its own field. The first valid account
    # number in document order wins, and the sentence-level fallback recovers
    # the holder.
    fields = extract_fields(
        PARALLEL_GENERATIONS_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS AUTHORITY"
    assert fields["account_number"] == "00112233445566"


def test_extract_skips_old_and_new_prefixed_generation_labels():
    # The real DG_Sports AMC's first and third generation labels are prefixed
    # with "Old"/"New" ("Old Account No (U-Bank Plus)", "New Account No.
    # (T-24 Islamic)") -- they must NOT be read as the anchored account-number
    # label (the anchor pattern matches from the start of the line, so "Old
    # Account No" and "New Account No" do not match it), and their values must
    # not be captured. The first genuinely anchored "Account No. (T-24
    # System)" block wins, and its IBAN must come from that same generation
    # (not an older/newer one).
    fields = extract_fields(
        PREFIXED_GENERATIONS_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS COMPLEX"
    assert fields["account_number"] == "00112233445561"
    assert fields["iban"] == "PK99FAKE0200010000000001"


def test_extract_old_prefixed_block_before_anchored_block_does_not_win():
    # Even when an "Old Account No (U-Bank Plus)" block appears BEFORE the
    # genuinely anchored "Account No." block in document order, the prefixed
    # label is not an account-number anchor, so the anchored block still wins.
    # This pins the real DG_Sports shape: the old-generation value must never
    # leak in as the account number.
    fields = extract_fields(
        OLD_PREFIX_BEFORE_ANCHORED_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS COMPLEX"
    assert fields["account_number"] == "00112233445561"
    assert fields["iban"] == "PK99FAKE0200010000000001"


def test_extract_holder_from_sentence_only_no_false_positive():
    # The sentence fallback must not fire on prose that merely mentions the
    # word "account" without ownership ("account is maintained with us") and
    # must not surface a placeholder or bank-name noise as the holder.
    fields = extract_fields(
        SENTENCE_NO_OWNERSHIP_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_number"] == "00112233445566"
    assert "account_holder" not in fields


def test_extract_account_number_from_ocr_noise_prose_tail():
    # A qualifier-stripped OCR line whose trailing prose ("...titled as Tehsil
    # General Account") is not part of the number must still yield the real
    # IBAN-shaped token, never a prose-laden account_number value.
    fields = extract_fields(
        PAREN_IBAN_OCR_NOISE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_number"] == "PK99FAKE0000000000000000"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_holder_from_subject_verb_sentence():
    # The real DG_Sports/GDA AMC certifying sentence states the holder as the
    # subject ("It is certified that [ORG] maintaining account with ..."),
    # opposite word order from the "account of X" patterns. The subject-verb
    # pattern must recover it when no labeled holder exists.
    fields = extract_fields(
        SUBJECT_VERB_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS AUTHORITY"
    assert fields["account_number"] == "00112233445566"


def test_extract_holder_from_is_maintaining_sentence():
    # The same subject-verb shape with an explicit "is" ("... is maintaining a
    # ... Account") must also match.
    fields = extract_fields(
        SUBJECT_VERB_IS_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS AUTHORITY"
    assert fields["account_number"] == "00112233445566"


def test_extract_holder_from_title_case_subject_verb_sentence():
    # The real DG_Sports AMC states the holder in Title Case ("certify that
    # Sample Sports Complex is maintaining ...") with no labeled holder field;
    # the sentence capture must accept mixed-case names, not just ALL-CAPS.
    fields = extract_fields(
        SUBJECT_VERB_TITLE_CASE_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "Sample Sports Complex"
    assert fields["account_number"] == "00112233445566"


def test_extract_holder_sentence_rejects_bank_as_subject():
    # "We are maintaining the above mentioned account in our branch" names no
    # holder; the subject is the bank/branch itself, which the sentence path
    # must not surface as an account holder (labeled titles are unaffected).
    fields = extract_fields(
        WE_ARE_MAINTAINING_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_number"] == "00112233445566"
    assert "account_holder" not in fields


def test_extract_wrapped_parenthetical_title_stops_at_balance():
    # A wrapped parenthetical title is complete once its closing paren is
    # consumed; a trailing unrelated all-caps line must not be absorbed.
    # (GDA copy3's "DG GDA (GALIYAT DEVELOPMENT AUTHORITY)" followed by
    # "DEVELOPMENT FUND".)
    fields = extract_fields(
        BALANCED_PAREN_TITLE_STOP_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS (SAMPLE DEVELOPMENT AUTHORITY)"
    assert "SAMPLE FUND" not in fields["account_holder"]
    assert fields["account_number"] == "1234567890"


def test_checklist_field_labels_never_route_into_keyword_detection():
    # The Account Maintenance Certificate's own field labels ("IBAN",
    # "Account Number") are close enough to the bank-statement keyword table
    # that OCR keyword detection misclassifies it. This is exactly why the
    # service routes checklist types from the splitter's own classification
    # *before* keyword detection -- so the assertion below documents the
    # hazard rather than the expected classification.
    assert (
        detect_document_type(ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT)
        is not AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    )


def test_extract_brd_fields_prose_form():
    fields = extract_fields(
        BRD_TEXT_PROSE_FORM, AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert fields["revenue_services_listed"] == "prescribed fees"


def test_extract_brd_fields_numbered_list_form():
    fields = extract_fields(
        BRD_TEXT_NUMBERED_LIST_FORM,
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FIN TECH UNIT"
    assert fields["revenue_services_listed"] == "sources of Income"


def test_extract_brd_fields_categorized_bullets_form():
    fields = extract_fields(
        BRD_TEXT_CATEGORIZED_BULLETS_FORM,
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert fields["revenue_services_listed"] == "SERVICES OFFERED"


def test_brd_missing_digitization_mention_is_missing_not_invalid():
    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    fields = extract_fields(BRD_TEXT_NO_DIGITIZATION_MENTION, document_type)
    assert "digitization_intent_confirmed" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["digitization_intent_confirmed"]["status"] == "missing"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # digitization_intent_confirmed is critical -- its absence must force
    # manual review, not a silent pass.
    assert status is VerificationStatus.NEEDS_REVIEW


def test_brd_missing_services_list_is_visible_but_not_blocking():
    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    fields = extract_fields(BRD_TEXT_NO_SERVICES_MENTION, document_type)
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert "revenue_services_listed" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    # revenue_services_listed is non-critical, but Section 10 requires it --
    # its absence must still surface to a reviewer as "missing", not vanish
    # from the results just because it isn't critical.
    assert by_field["revenue_services_listed"]["status"] == "missing"
    assert by_field["digitization_intent_confirmed"]["status"] == "valid"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # Non-critical, so this alone must not force NEEDS_REVIEW -- but it must
    # still cost something: not a full VERIFIED pass either.
    assert status is not VerificationStatus.NEEDS_REVIEW
    assert status is not VerificationStatus.VERIFIED


def test_brd_validators_and_scoring():
    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    fields = extract_fields(BRD_TEXT_NUMBERED_LIST_FORM, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["digitization_intent_confirmed"]["status"] == "valid"
    assert by_field["revenue_services_listed"]["status"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_onelink_letter_fields_single_account_form():
    # branch_code and iban were both deliberately dropped from this
    # extractor 2026-08-19 (department decision, see CONTEXT.md) -- kept as
    # a real, distinct fixture only to confirm organization_name still
    # extracts cleanly from this shape and nothing else is invented.
    fields = extract_fields(
        ONE_LINK_LETTER_TEXT_SINGLE_ACCOUNT, AnalyzedDocumentType.ONE_LINK_LETTER
    )
    assert fields["organization_name"] == "SAMPLE TEHSIL MUNICIPAL ADMINISTRATION"
    assert "branch_code" not in fields


def test_extract_onelink_letter_fields_multi_bank_table_form():
    document_type = AnalyzedDocumentType.ONE_LINK_LETTER
    fields = extract_fields(ONE_LINK_LETTER_TEXT_MULTI_BANK_TABLE, document_type)
    assert fields["organization_name"] == "SAMPLE DEVELOPMENT AUTHORITY"
    assert "branch_code" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["organization_name"] == "valid"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    assert status is not VerificationStatus.NEEDS_REVIEW


def test_onelink_letter_missing_organization_name_forces_review():
    document_type = AnalyzedDocumentType.ONE_LINK_LETTER
    fields = extract_fields(ONE_LINK_LETTER_TEXT_NO_ORG_NAME, document_type)
    assert "organization_name" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["organization_name"] == "missing"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # organization_name is critical -- its absence must force manual review.
    assert status is VerificationStatus.NEEDS_REVIEW


def test_onelink_letter_validators_and_scoring():
    document_type = AnalyzedDocumentType.ONE_LINK_LETTER
    fields = extract_fields(ONE_LINK_LETTER_TEXT_SINGLE_ACCOUNT, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["organization_name"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no cross-document rule watches this type's fields

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score == 1.0
    assert status is VerificationStatus.VERIFIED


def test_extract_cnic_front_fields_clean_layout():
    fields = extract_fields(CNIC_FRONT_TEXT_CLEAN, AnalyzedDocumentType.CNIC_FRONT)
    assert fields["document_number"] == "12345-1234567-1"
    assert fields["full_name"] == "Samia Naz"
    assert fields["date_of_expiry"] == "2030-01-01"


def test_extract_cnic_front_fields_scrambled_layout():
    document_type = AnalyzedDocumentType.CNIC_FRONT
    fields = extract_fields(CNIC_FRONT_TEXT_SCRAMBLED, document_type)
    # document_number (format-anchored) and full_name (lucky adjacency, same
    # as the real scrambled sample) still extract correctly.
    assert fields["document_number"] == "12345-1234567-1"
    assert fields["full_name"] == "Samia Naz"
    # date_of_expiry's two-label/two-value block never occurs intact here --
    # must honestly miss, not guess from out-of-order values.
    assert "date_of_expiry" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["date_of_expiry"] == "missing"
    assert by_field["document_number"] == "valid"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # date_of_expiry is non-critical, so its absence alone must not force review.
    assert status is not VerificationStatus.NEEDS_REVIEW


def test_cnic_front_missing_name_does_not_force_review():
    document_type = AnalyzedDocumentType.CNIC_FRONT
    fields = extract_fields(CNIC_FRONT_TEXT_NO_NAME, document_type)
    assert "full_name" not in fields
    assert fields["document_number"] == "12345-1234567-1"
    assert fields["date_of_expiry"] == "2030-01-01"

    validations = ValidatorEngine().run(document_type, fields)
    consistency = RulesEngine().run(document_type, fields)
    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    # full_name is non-critical -- its absence alone must not force review,
    # even though the fleet-wide field-coverage score dips below VERIFIED.
    assert status is VerificationStatus.PARTIALLY_VERIFIED


def test_cnic_front_missing_document_number_forces_review():
    document_type = AnalyzedDocumentType.CNIC_FRONT
    text = "PAKISTAN\nNational Identity Card\nName\nSamia Naz\n"
    fields = extract_fields(text, document_type)
    assert "document_number" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["document_number"] == "missing"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # document_number is critical -- its absence must force manual review.
    assert status is VerificationStatus.NEEDS_REVIEW


def test_parse_amount_variants():
    assert _parse_amount("1,250.50") == 1250.5
    assert _parse_amount("1.250,50") == 1250.5
    assert _parse_amount("2,500.00") == 2500.0
    assert _parse_amount("549.75") == 549.75
    assert _parse_amount("EUR 45,000.00") == 45000.0
    assert _parse_amount("1,000") == 1000.0
    assert _parse_amount("0.99") == 0.99
    assert _parse_amount("garbage") is None


# --- Validators --------------------------------------------------------------


def test_validate_iban_valid():
    status, message = validate_iban("DE89370400440532013000")
    assert status == "valid"
    assert "checksum passed" in message


def test_validate_iban_invalid_checksum():
    status, _ = validate_iban("DE89370400440532013001")
    assert status == "invalid"


def test_validate_iban_invalid_format():
    assert validate_iban("12")[0] == "invalid"
    assert validate_iban("DE00")[0] == "invalid"


def test_validate_currency():
    assert validate_currency("EUR")[0] == "valid"
    assert validate_currency("eur")[0] == "invalid"
    assert validate_currency("EURO")[0] == "invalid"


def test_validate_account_number():
    assert validate_account_number("1234567890")[0] == "valid"
    assert validate_account_number("12")[0] == "invalid"
    assert validate_account_number("1234 5678 90")[0] == "valid"


def test_validate_date_accepts_future_expiry():
    assert validate_date("2028-06-01")[0] == "valid"
    assert validate_date("not-a-date")[0] == "invalid"


def test_validate_date_not_future_rejects_future():
    assert validate_date_not_future("1990-05-15")[0] == "valid"
    assert validate_date_not_future("2099-01-01")[0] == "invalid"


def test_validate_salary_month():
    assert validate_salary_month("2026-01")[0] == "valid"
    assert validate_salary_month("2026-13")[0] == "invalid"
    assert validate_salary_month("01/2026")[0] == "invalid"


def test_validator_engine_reports_missing_fields():
    text = """BANK STATEMENT
    Account Number: 1234567890
    Closing Balance: 5,000.00
    """
    document_type, fields, validations, _ = _components(text)
    assert document_type is AnalyzedDocumentType.BANK_STATEMENT
    assert fields["account_number"] == "1234567890"
    statuses = {result["field"]: result["status"] for result in validations}
    assert statuses["account_holder"] == "missing"
    assert statuses["opening_balance"] == "missing"
    assert any(result["message"] == "Account holder missing" for result in validations)


# --- Consistency rules -------------------------------------------------------


def test_rule_reconciliation_passes_with_credits_and_debits():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "pass"


def test_rule_reconciliation_fails_on_mismatch():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    fields["closing_balance"] = 9999.99
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "fail"


def test_rule_zero_transactions_keeps_balance():
    text = BANK_STATEMENT_TEXT.replace("Transactions: 23", "Transactions: 0")
    text = text.replace("Total Credits: 2,500.00", "Total Credits: -")
    text = text.replace("Total Debits: 549.75", "Total Debits: -")
    fields = extract_fields(text, AnalyzedDocumentType.BANK_STATEMENT)
    fields["closing_balance"] = fields["opening_balance"]
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "pass"


def test_rule_net_le_gross_fails():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    fields["net_salary"] = 99999.0
    results = RulesEngine().run(AnalyzedDocumentType.PAYSLIP, fields)
    assert next(r for r in results if r["rule_id"] == "NET_LE_GROSS")["status"] == "fail"


def test_rule_payment_date_outside_month_fails():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    fields["payment_date"] = "2026-06-15"
    results = RulesEngine().run(AnalyzedDocumentType.PAYSLIP, fields)
    rule = next(r for r in results if r["rule_id"] == "PAYMENT_WITHIN_MONTH")
    assert rule["status"] == "fail"


def test_rule_expiry_before_issue_fails():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    fields["issue_date"] = "2030-01-01"
    results = RulesEngine().run(AnalyzedDocumentType.ID_DOCUMENT, fields)
    rule = next(r for r in results if r["rule_id"] == "EXPIRY_AFTER_ISSUE")
    assert rule["status"] == "fail"


def test_rule_age_reasonable():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    results = RulesEngine().run(AnalyzedDocumentType.ID_DOCUMENT, fields)
    assert next(r for r in results if r["rule_id"] == "AGE_REASONABLE")["status"] == "pass"


# --- Scoring -----------------------------------------------------------------


def test_compute_score_is_weighted():
    score = compute_score(field_coverage=1.0, validation_rate=1.0, consistency_rate=1.0)
    assert score == 1.0
    score = compute_score(field_coverage=0.5, validation_rate=0.5, consistency_rate=0.5)
    assert score == 0.5
    score = compute_score(field_coverage=0.0, validation_rate=1.0, consistency_rate=1.0)
    assert score == 0.5


def test_compute_score_clamps():
    assert compute_score(field_coverage=2.0, validation_rate=2.0, consistency_rate=2.0) == 1.0
    assert compute_score(field_coverage=-1.0, validation_rate=0.0, consistency_rate=0.0) == 0.0


def test_status_derivation_branches():
    assert compute_verification_status(0.9, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.VERIFIED
    assert compute_verification_status(0.7, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.PARTIALLY_VERIFIED
    assert compute_verification_status(0.5, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.2, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.FAILED


def test_status_forced_to_needs_review():
    assert compute_verification_status(0.95, missing_critical_fields=True,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.95, missing_critical_fields=False,
                                      critical_validation_failures=True,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.95, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=True) is VerificationStatus.NEEDS_REVIEW


def test_scoring_components_full_statement_verifies():
    document_type, fields, validations, consistency = _components(BANK_STATEMENT_TEXT)
    coverage, v_rate, c_rate, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert coverage == 1.0
    assert v_rate == 1.0
    assert c_rate == 1.0
    assert score == 1.0
    assert status is VerificationStatus.VERIFIED


def test_scoring_components_missing_critical_field():
    text = BANK_STATEMENT_TEXT.replace("Opening Balance: 1,250.50", "Opening Balance: -")
    document_type, fields, validations, consistency = _components(text)
    _, _, _, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score < 1.0
    assert status is VerificationStatus.NEEDS_REVIEW


def test_issues_are_human_readable():
    text = BANK_STATEMENT_TEXT.replace("Opening Balance: 1,250.50", "Opening Balance: -")
    document_type, _, validations, consistency = _components(text)
    issues = [
        v["message"] for v in validations if v["status"] != "valid"
    ] + [c["message"] for c in consistency if c["status"] != "pass"]
    assert any("Opening balance missing" in message for message in issues)


# --- Repository --------------------------------------------------------------


def _seed_application_and_document() -> tuple[int, int]:
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="repo-test")
        document = DocumentRepository(db).create(
            application_id=application.id,
            document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            original_filename="statement.pdf",
            stored_file_path="applications/APP-test/statement.pdf",
            file_type="application/pdf",
        )
        return application.id, document.id
    finally:
        db.close()


def _seed_amc_document_with_ocr() -> tuple[int, int]:
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="repo-test")
        document = DocumentRepository(db).create(
            application_id=application.id,
            document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            original_filename="amc.pdf",
            stored_file_path="applications/APP-test/amc.pdf",
            file_type="application/pdf",
        )
        OCRRepository(db).create(
            document_id=document.id,
            raw_ocr_text=ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT,
            ocr_engine="test",
        )
        return application.id, document.id
    finally:
        db.close()


def test_amc_document_is_routed_before_keyword_detection():
    # The AMC OCR text alone would keyword-detect as a generic category (see
    # test_checklist_field_labels_never_route_into_keyword_detection); the
    # service must trust the splitter's storage-level classification instead
    # and run the AMC extractor against it.
    application_id, document_id = _seed_amc_document_with_ocr()
    db = SessionLocal()
    try:
        response = DocumentAnalysisService(db).analyze(application_id=application_id)
        item = next(i for i in response.items if i.document_id == document_id)
        assert item.outcome is AnalysisOutcome.ANALYZED
        row = DocumentAnalysisRepository(db).get_by_document(document_id)
        assert (
            row.document_type
            == AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE.value
        )
        assert row.extracted_fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
        assert row.extracted_fields["iban"] == "PK36FUTB0000001123456702"
    finally:
        db.close()


def test_repository_upsert_creates_then_updates():
    application_id, document_id = _seed_application_and_document()
    db = SessionLocal()
    try:
        repository = DocumentAnalysisRepository(db)
        first = repository.upsert(
            application_id=application_id,
            document_id=document_id,
            document_type=AnalyzedDocumentType.BANK_STATEMENT.value,
            extracted_fields={"account_number": "123"},
            validation_results=[{"field": "account_number", "status": "valid"}],
            consistency_results=[],
            confidence_score=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED.value,
            analysis_version="1.0.0",
            processing_time_ms=10,
        )
        assert repository.get_by_document(document_id) is first
        updated = repository.upsert(
            application_id=application_id,
            document_id=document_id,
            document_type=AnalyzedDocumentType.BANK_STATEMENT.value,
            extracted_fields={"account_number": "456", "iban": "DE..."},
            validation_results=[{"field": "account_number", "status": "valid"}],
            consistency_results=[],
            confidence_score=0.9,
            verification_status=VerificationStatus.VERIFIED.value,
            analysis_version="1.0.0",
            processing_time_ms=20,
        )
        assert updated.id == first.id
        results = repository.get_by_application(application_id)
        assert len(results) == 1
        assert results[0].extracted_fields == {"account_number": "456", "iban": "DE..."}
        assert results[0].confidence_score == 0.9
        assert results[0].verification_status == VerificationStatus.VERIFIED.value
    finally:
        db.close()
