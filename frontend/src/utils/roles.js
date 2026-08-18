/**
 * Canonical operational roles, mirroring backend/app/auth/roles.py.
 *
 * Roles are stored on `users.role` as a free-form string (the backend has no
 * role enum). This module mirrors the backend's `effective_role` mapping so the
 * frontend gates UI affordances (operator actions, IT log viewer) on the same
 * canonical role the backend enforces. The backend 403 remains authoritative
 * -- this only decides what the UI shows, never what the backend allows.
 */
export const ROLE_OPERATOR = 'OPERATOR';
export const ROLE_REVIEWER = 'REVIEWER';
export const ROLE_IT = 'IT';

//: Legacy role strings mapped to the canonical role they imply. The seeded
//: default account historically used "Verification Officer" and performs the
//: human-verification (review) workflow, so it maps to REVIEWER.
const ROLE_GROUPS = {
  'Verification Officer': ROLE_REVIEWER,
};

const CANONICAL_ROLES = new Set([ROLE_OPERATOR, ROLE_REVIEWER, ROLE_IT]);

/**
 * Resolve a stored role string to its canonical role.
 *
 * Matches backend `effective_role`: unrecognized strings pass through unchanged,
 * the empty/missing role defaults to OPERATOR (same as the backend default).
 *
 * @param {string|null|undefined} role Stored `users.role` value, if any.
 * @returns {string} The canonical role.
 */
export function effectiveRole(role) {
  if (!role) {
    return ROLE_OPERATOR;
  }
  if (CANONICAL_ROLES.has(role)) {
    return role;
  }
  return ROLE_GROUPS[role] ?? role;
}

/** Return whether the user holds the operator role. */
export function isOperator(user) {
  return effectiveRole(user?.role) === ROLE_OPERATOR;
}

/** Return whether the user holds the reviewer role. */
export function isReviewer(user) {
  return effectiveRole(user?.role) === ROLE_REVIEWER;
}

/** Return whether the user holds the IT role. */
export function isIt(user) {
  return effectiveRole(user?.role) === ROLE_IT;
}