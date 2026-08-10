// Types matching the Python Pydantic schemas

export type VerificationStatus = 'PASS' | 'WARNING' | 'MANUAL_REVIEW' | 'FAIL' | 'REJECTED';

export interface RuleCheckResult {
  rule_id: string;
  rule_name: string;
  document_type: string;
  status: VerificationStatus;
  message: string;
  confidence?: number;
  field_value?: string;
  expected_value?: string;
}

export interface CrossDocumentMatch {
  field_name: string;
  documents_compared: string[];
  values_found: Record<string, string>;
  is_consistent: boolean;
  status: VerificationStatus;
  message: string;
}

export interface DocumentVerificationResult {
  document_type: string;
  file_name: string;
  rule_results: RuleCheckResult[];
  pass_count: number;
  fail_count: number;
  warning_count: number;
  manual_review_count: number;
  overall_status: VerificationStatus;
}

export interface VerificationReport {
  case_id: string;
  organization_name: string;
  submitted_at: string;
  verified_at?: string;
  document_results: DocumentVerificationResult[];
  cross_document_checks: CrossDocumentMatch[];
  total_rules_checked: number;
  total_pass: number;
  total_fail: number;
  total_warnings: number;
  total_manual_review: number;
  overall_status: VerificationStatus;
  reviewer_notes?: string;
  reviewed_by?: string;
}

export const mockCases: VerificationReport[] = [
  {
    case_id: 'CASE-2026-A101',
    organization_name: 'TechFin Solutions (Pvt) Ltd',
    submitted_at: '2026-08-10T09:15:00Z',
    overall_status: 'MANUAL_REVIEW',
    total_rules_checked: 24,
    total_pass: 21,
    total_fail: 0,
    total_warnings: 1,
    total_manual_review: 2,
    cross_document_checks: [
      {
        field_name: 'account_number',
        documents_compared: ['account_maintenance_certificate', 'tripartite_agreement'],
        values_found: {
          'account_maintenance_certificate': '0123456789',
          'tripartite_agreement': '0123-456789'
        },
        is_consistent: false,
        status: 'MANUAL_REVIEW',
        message: 'Formatting differs slightly, requires human confirmation.'
      }
    ],
    document_results: [
      {
        document_type: 'tripartite_agreement',
        file_name: 'tripartite_signed.pdf',
        overall_status: 'MANUAL_REVIEW',
        pass_count: 5, fail_count: 0, warning_count: 0, manual_review_count: 1,
        rule_results: [
          {
            rule_id: 'TRI_001_BLANK_DATE',
            rule_name: 'Preamble Date Must Be Blank',
            document_type: 'tripartite_agreement',
            status: 'PASS',
            message: 'Preamble date is correctly left blank.'
          },
          {
            rule_id: 'TRI_002_SIGNATURES',
            rule_name: 'All Parties Signed',
            document_type: 'tripartite_agreement',
            status: 'MANUAL_REVIEW',
            message: 'KPITB signature detected, but OCR confidence is low.',
            confidence: 0.42
          }
        ]
      },
      {
        document_type: 'e_stamp_paper',
        file_name: 'estamp_scan.pdf',
        overall_status: 'WARNING',
        pass_count: 3, fail_count: 0, warning_count: 1, manual_review_count: 0,
        rule_results: [
          {
            rule_id: 'EST_001_TEXTURE',
            rule_name: 'E-Stamp Texture Match',
            document_type: 'e_stamp_paper',
            status: 'WARNING',
            message: 'Background lacks typical brownish texture, may be a black-and-white printout.'
          }
        ]
      }
    ]
  },
  {
    case_id: 'CASE-2026-B205',
    organization_name: 'Global Pay Connect',
    submitted_at: '2026-08-10T11:30:00Z',
    overall_status: 'FAIL',
    total_rules_checked: 24,
    total_pass: 22,
    total_fail: 2,
    total_warnings: 0,
    total_manual_review: 0,
    cross_document_checks: [],
    document_results: [
      {
        document_type: 'tripartite_agreement',
        file_name: 'agreement_final.pdf',
        overall_status: 'FAIL',
        pass_count: 4, fail_count: 1, warning_count: 0, manual_review_count: 0,
        rule_results: [
          {
            rule_id: 'TRI_001_BLANK_DATE',
            rule_name: 'Preamble Date Must Be Blank',
            document_type: 'tripartite_agreement',
            status: 'FAIL',
            message: 'The preamble date was filled in, which violates KPITB rules.',
            field_value: 'March 14, 2025',
            expected_value: 'Blank'
          }
        ]
      },
      {
        document_type: 'bilateral_agreement',
        file_name: 'sla_doc.pdf',
        overall_status: 'FAIL',
        pass_count: 4, fail_count: 1, warning_count: 0, manual_review_count: 0,
        rule_results: [
          {
            rule_id: 'BIL_002_PLATFORM',
            rule_name: 'Platform Explicitly Mentioned',
            document_type: 'bilateral_agreement',
            status: 'FAIL',
            message: 'Required platform name not found in the SLA text.',
            field_value: 'N/A',
            expected_value: 'PayMin | Digital Muhasil | Paymere BCX'
          }
        ]
      }
    ]
  },
  {
    case_id: 'CASE-2026-C991',
    organization_name: 'Crescent Fintech Services',
    submitted_at: '2026-08-09T16:45:00Z',
    overall_status: 'PASS',
    total_rules_checked: 24,
    total_pass: 24,
    total_fail: 0,
    total_warnings: 0,
    total_manual_review: 0,
    cross_document_checks: [],
    document_results: []
  }
];
