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
  pageCount: 1,
  currentPage: 0,
  onFilterChange: vi.fn(),
  onReset: vi.fn(),
  onSearch: vi.fn(),
  onGoToPage: vi.fn(),
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

  it('lets the all-access Employee account view the system logs', () => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [makeEntry()],
      total: 1,
    });

    renderPage();

    expect(screen.queryByText(/access denied/i)).not.toBeInTheDocument();
    expect(screen.getByText('operator1')).toBeInTheDocument();
    expect(screen.getByText(/1 entry/i)).toBeInTheDocument();
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

  it('shows the status transition column when a status change is recorded', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [
        makeEntry({
          previous_status: 'SUBMITTED',
          new_status: 'PROCESSING',
        }),
      ],
      total: 1,
    });

    renderPage();

    expect(screen.getByText('Submitted')).toBeInTheDocument();
    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();
  });

  it('shows a dash for the status column when no status change was recorded', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [makeEntry({ previous_status: null, new_status: null })],
      total: 1,
    });

    renderPage();

    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('—');
  });

  it('expands and collapses an entry to reveal structured details', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [makeEntry()],
      total: 1,
    });

    renderPage();

    const expandButton = screen.getByRole('button', { name: /show event details/i });
    fireEvent.click(expandButton);

    expect(screen.getByText(/event details/i)).toBeInTheDocument();
    expect(screen.getByText(/"application_name": "TMA Khal"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /hide event details/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /hide event details/i }));
    expect(screen.queryByText(/event details/i)).not.toBeInTheDocument();
  });

  it('does not offer expansion when the entry has no structured details', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [
        makeEntry({ details: null, previous_status: null, new_status: null }),
      ],
      total: 1,
    });

    renderPage();

    expect(screen.queryByRole('button', { name: /show event details/i })).not.toBeInTheDocument();
  });

  it('pages through multiple result pages', async () => {
    const onGoToPage = vi.fn();

    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      entries: [makeEntry()],
      total: 150,
      pageCount: 3,
      currentPage: 1,
      onGoToPage,
    });

    renderPage();

    expect(screen.getByText(/page 2 of 3/i)).toBeInTheDocument();
    expect(screen.getAllByText(/150 entries/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /next page/i }));
    await waitFor(() => expect(onGoToPage).toHaveBeenCalledWith(2));

    fireEvent.click(screen.getByRole('button', { name: /previous page/i }));
    await waitFor(() => expect(onGoToPage).toHaveBeenCalledWith(0));
  });

  it('filters by event type via a free-text input', async () => {
    const onFilterChange = vi.fn();

    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({ ...baseHookValue, onFilterChange });

    renderPage();

    const input = screen.getByLabelText(/event type/i);
    fireEvent.change(input, { target: { value: 'human_review.submitted' } });

    await waitFor(() =>
      expect(onFilterChange).toHaveBeenCalledWith('eventType', 'human_review.submitted')
    );
  });
});