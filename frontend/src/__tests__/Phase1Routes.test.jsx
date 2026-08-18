import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import App from '../App';

vi.mock('../auth/authService', () => ({
  getCurrentUser: vi.fn(() =>
    Promise.resolve({ user: { id: 1, name: 'Test Operator', role: 'Verification Officer' } })
  ),
  login: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
}));

vi.mock('../services/applications', () => ({
  listApplications: vi.fn(() => Promise.resolve({ items: [] })),
  createApplication: vi.fn(),
}));

vi.mock('../services/operatorWorkflow', () => ({
  listValidationQueue: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  getValidationHistory: vi.fn(() => Promise.resolve({ entries: [], total: 0 })),
  requestDocuments: vi.fn(),
  rejectApplication: vi.fn(),
  submitApplication: vi.fn(),
}));

vi.mock('../services/systemLogs', () => ({
  searchSystemLogs: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  getSystemLog: vi.fn(),
}));

describe('Phase 1 frontend routes', () => {
  it('renders the Validation page at /validation', async () => {
    render(
      <MemoryRouter initialEntries={['/validation']}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByText(/no applications to validate/i)
    ).toBeInTheDocument();
  });

  it('renders the System Logs page at /settings/system-logs', async () => {
    render(
      <MemoryRouter initialEntries={['/settings/system-logs']}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByText(/no audit records match the current filters/i)
    ).toBeInTheDocument();
  });
});