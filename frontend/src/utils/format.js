/**
 * Format an ISO datetime string as a readable date, e.g. "Aug 7, 2026".
 *
 * @param {string | null | undefined} iso The value to format.
 * @returns {string} A formatted date, or an en-dash when empty.
 */
export function formatDate(iso) {
  if (!iso) {
    return '\u2014';
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '\u2014'
    : date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
}

/**
 * Format an ISO datetime string with a time component, e.g. "Aug 7, 2026, 2:30 PM".
 *
 * @param {string | null | undefined} iso The value to format.
 * @returns {string} A formatted datetime, or an en-dash when empty.
 */
export function formatDateTime(iso) {
  if (!iso) {
    return '\u2014';
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '\u2014'
    : date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
}

/**
 * Turn a SCREAMING_SNAKE_CASE backend enum value into a readable label,
 * e.g. "document_completeness" -> "Document Completeness".
 *
 * @param {string | null | undefined} value The raw enum value.
 * @returns {string} A title-cased label, or an en-dash when empty.
 */
export function humanizeEnum(value) {
  if (!value) {
    return '\u2014';
  }
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
