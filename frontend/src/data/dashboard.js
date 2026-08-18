import {
  Activity,
  ClipboardCheck,
  FileText,
  FolderOpen,
  Plus,
  ScrollText,
  UserCheck,
} from 'lucide-react';
import { isEmployee, isIt, isOperator, isReviewer } from '../utils/roles';

/**
 * Static profile shown in the sidebar footer and the top navigation bar.
 * Real authentication lands in a later phase; this is presentational data
 * belonging to the dashboard layout shell.
 */
export const USER_PROFILE = {
  name: 'Employee',
  role: 'Verification Officer',
  initials: 'EM',
  online: true,
};

/**
 * Shared Quick Action definitions, keyed by id.
 *
 * Only the `label`/`to`/`icon` are fixed per action; each role list in
 * `DASHBOARD_ACTIONS` overrides the description so the same action reads
 * differently depending on who is looking at it.
 */
const ACTION_DEFS = {
  'new-application': {
    id: 'new-application',
    label: 'New Application',
    to: '/applications/new',
    icon: Plus,
  },
  'view-applications': {
    id: 'view-applications',
    label: 'View Applications',
    to: '/applications',
    icon: FolderOpen,
  },
  validation: {
    id: 'validation',
    label: 'Open Validation',
    to: '/validation',
    icon: ClipboardCheck,
  },
  'validation-report': {
    id: 'validation-report',
    label: 'Open Validation Report',
    to: '/reports',
    icon: FileText,
  },
  'human-review': {
    id: 'human-review',
    label: 'Open Human Review',
    to: '/human-review',
    icon: UserCheck,
  },
  processing: {
    id: 'processing',
    label: 'Processing',
    to: '/processing',
    icon: Activity,
  },
  'system-logs': {
    id: 'system-logs',
    label: 'System Logs',
    to: '/settings/system-logs',
    icon: ScrollText,
  },
};

/**
 * Dashboard Quick Actions per canonical role.
 *
 * Navigation visibility only -- the backend 403 stays authoritative. The
 * Employee (testing/supervisor) account sees every shortcut; Operator handles
 * intake + validation + processing; Reviewer reviews validated applications;
 * IT monitors processing and system activity. Roles that cannot create an
 * application do not get a "New Application" shortcut at all.
 */
export const DASHBOARD_ACTIONS = {
  EMPLOYEE: [
    { ...ACTION_DEFS['new-application'], description: 'Start a new document verification case.' },
    { ...ACTION_DEFS['view-applications'], description: 'Browse and manage existing applications.' },
    { ...ACTION_DEFS.validation, description: 'Check document completeness and handle missing documents.' },
    { ...ACTION_DEFS['validation-report'], description: 'Inspect validation results and document issues.' },
    { ...ACTION_DEFS['human-review'], description: 'Make the final decision on an application.' },
    { ...ACTION_DEFS['system-logs'], description: 'View system activity and audit logs.' },
  ],
  OPERATOR: [
    { ...ACTION_DEFS['new-application'], description: 'Start a new document verification case.' },
    { ...ACTION_DEFS['view-applications'], description: 'Browse and manage existing applications.' },
    { ...ACTION_DEFS.validation, description: 'Check document completeness and handle missing documents.' },
    { ...ACTION_DEFS.processing, description: 'Monitor document processing progress.' },
  ],
  REVIEWER: [
    { ...ACTION_DEFS['view-applications'], description: 'Browse applications assigned for verification.' },
    { ...ACTION_DEFS['validation-report'], description: 'Inspect validation results and document issues.' },
    { ...ACTION_DEFS['human-review'], description: 'Review documents and make the final decision.' },
    { ...ACTION_DEFS.processing, description: 'View the processing status of applications.' },
  ],
  IT: [
    { ...ACTION_DEFS['view-applications'], description: 'Monitor application records and current status.' },
    { ...ACTION_DEFS.processing, description: 'Monitor document processing activity.' },
    { ...ACTION_DEFS['system-logs'], description: 'Inspect system activity and audit logs.' },
  ],
};

/**
 * Resolve the Quick Actions for a user's canonical role.
 *
 * Employee takes precedence so the full-access testing account sees everything
 * even if its stored role string happens to overlap a canonical role mapping.
 * Falls back to the OPERATOR set (same default as `effectiveRole`).
 *
 * @param {object|null|undefined} user The current user, if any.
 * @returns {Array} The Quick Action cards for that role.
 */
export function getDashboardActions(user) {
  if (isEmployee(user)) return DASHBOARD_ACTIONS.EMPLOYEE;
  if (isOperator(user)) return DASHBOARD_ACTIONS.OPERATOR;
  if (isReviewer(user)) return DASHBOARD_ACTIONS.REVIEWER;
  if (isIt(user)) return DASHBOARD_ACTIONS.IT;
  return DASHBOARD_ACTIONS.OPERATOR;
}

/**
 * Role-specific dashboard welcome description, mirroring what each role is
 * here to do. The heading ("Welcome back!") stays identical for everyone.
 */
export const DASHBOARD_WELCOME = {
  EMPLOYEE: "Here's an overview of your financial document verification workspace.",
  OPERATOR: 'Manage document intake, completeness checks, and application processing.',
  REVIEWER: 'Review validated applications and make final verification decisions.',
  IT: 'Monitor application processing and system activity.',
};

/**
 * Resolve the dashboard welcome description for a user's canonical role.
 *
 * @param {object|null|undefined} user The current user, if any.
 * @returns {string} The welcome description for that role.
 */
export function getDashboardWelcome(user) {
  if (isEmployee(user)) return DASHBOARD_WELCOME.EMPLOYEE;
  if (isOperator(user)) return DASHBOARD_WELCOME.OPERATOR;
  if (isReviewer(user)) return DASHBOARD_WELCOME.REVIEWER;
  if (isIt(user)) return DASHBOARD_WELCOME.IT;
  return DASHBOARD_WELCOME.OPERATOR;
}