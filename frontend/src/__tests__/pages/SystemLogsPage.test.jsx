import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SystemLogsPage from '../../pages/SystemLogs/SystemLogsPage';

const { useSystemLogs, useAuth } = vi.hoisted(() => ({
  useSystemLogs: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/useSystemLogs', () => ({ useSystemLogs }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));

const baseHookValue = {
  entries: [],
  total: 0,
  loading: false,
  error: null,
  filters: {
    applicationId: '',
    actor: '',
    eventType: '',
    severity: '',
    dateFrom: '',
    dateTo: '',
    query: '',
  },
  onFilterChange: vi.fn(),
  onReset: vi.fn(),
  onSearch: vi.fn(),
};

function makeEntry(overrides = {}) {
  return {
    id: 1,
    application_id: 42,
    username: 'operator1',
    actor_role: 'OPERATOR',
    action: 'application.submitted',
    severity: 'INFO',
    previous_status: 'SUBMITTED',
    new_status: 'PROCESSING',
    document_id: null,
    performed_at: '2026-08-02T12:00:00Z',
    details: { application_name: 'TMA Khal' },
    ...overrides,
  };
}

function renderPage() {
  return render(<SystemLogsPage />);
}

describe('SystemLogsPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows an access-denied state for non-IT users', () => {
    useAuth.mockReturnValue({ user: { role: 'REVIEWER' } });
    useSystemLogs.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
    expect(screen.getByText(/restricted to the IT role/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders log entries for an IT user', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [makeEntry()],
      total: 1,
    });

    renderPage();

    expect(screen.getByText('operator1')).toBeInTheDocument();
    expect(screen.getByText(/1 entry/i)).toBeInTheDocument();
  });

  it('shows the empty state when no entries match the filters', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no log entries/i)).toBeInTheDocument();
  });

  it('shows the error state when the search fails', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({ ...baseHookValue, error: 'Network error' });

    renderPage();

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it('clears the filters on demand', async () => {
    const onReset = vi.fn();

    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({ ...baseHookValue, onReset });

    renderPage();

    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(onReset).toHaveBeenCalled());
  });
});