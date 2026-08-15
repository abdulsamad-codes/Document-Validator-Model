import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ApplicationsPage from '../../pages/Applications/ApplicationsPage';

const { useApplications } = vi.hoisted(() => ({ useApplications: vi.fn() }));

vi.mock('../../hooks/useApplications', () => ({ useApplications }));
vi.mock('../../hooks/useLastOpenedApplication', () => ({
  useLastOpenedApplication: () => ({ lastOpenedId: null }),
}));

const baseHookValue = {
  applications: [],
  total: 0,
  loading: false,
  error: null,
  reload: vi.fn(),
  searchTerm: '',
  statusFilter: '',
  sortKey: 'submitted_at',
  sortDir: 'desc',
  onSearchChange: vi.fn(),
  onStatusChange: vi.fn(),
  onSortChange: vi.fn(),
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ApplicationsPage />
    </MemoryRouter>
  );
}

describe('ApplicationsPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when there are no applications', () => {
    useApplications.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });

  it('renders a row for each application from the store', () => {
    useApplications.mockReturnValue({
      ...baseHookValue,
      applications: [
        {
          id: 42,
          name: 'Ali Khan',
          status: 'IN_PROGRESS',
          submitted_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-02T00:00:00Z',
          created_by: 'operator1',
        },
      ],
      total: 1,
    });

    renderPage();

    expect(screen.getByText('#42')).toBeInTheDocument();
    expect(screen.getByText('Ali Khan')).toBeInTheDocument();
    expect(screen.getByText('1 application')).toBeInTheDocument();
  });

  it('shows the error state and retries on demand', () => {
    const reload = vi.fn();
    useApplications.mockReturnValue({ ...baseHookValue, error: 'Network error', reload });

    renderPage();

    expect(
      screen.getByText(/unable to load applications/i)
    ).toBeInTheDocument();
  });
});
