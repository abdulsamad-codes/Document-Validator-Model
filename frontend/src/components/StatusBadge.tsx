import { type VerificationStatus } from '../data/mockSchemas';

interface StatusBadgeProps {
  status: VerificationStatus;
  className?: string;
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const getBadgeClass = (s: VerificationStatus) => {
    switch (s) {
      case 'PASS': return 'badge-pass';
      case 'WARNING': return 'badge-warning';
      case 'MANUAL_REVIEW': return 'badge-review';
      case 'FAIL': return 'badge-fail';
      case 'REJECTED': return 'badge-rejected';
      default: return 'bg-gray-500 text-white';
    }
  };

  const label = status.replace('_', ' ');

  return (
    <span className={`badge ${getBadgeClass(status)} ${className}`}>
      {label}
    </span>
  );
}
