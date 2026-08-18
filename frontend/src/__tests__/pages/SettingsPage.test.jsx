import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsPage from '../../pages/Settings/SettingsPage';

const { useAuth, useToast } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  useToast: vi.fn(),
}));

vi.mock('../../hooks/useAuth', () => ({ useAuth }));
vi.mock('../../components/common/Toast/ToastContext', () => ({ useToast }));
vi.mock('../../utils/preferences', () => ({
  getPreferences: vi.fn(() => ({})),
  setPreference: vi.fn(),
}));

const baseUser = {
  id: 1,
  employee_id: 'EMP-1001',
  email: 'employee@fintech.local',
  name: 'Test Employee',
  role: 'Verification Officer',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>
  );
}

describe('SettingsPage administration section', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the System Logs link for an IT user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'IT' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    const link = await screen.findByRole('link', { name: /system logs/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/settings/system-logs');
  });

  it('shows the System Logs link for the Employee (supervisor) account', async () => {
    useAuth.mockReturnValue({
      user: baseUser,
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    const link = await screen.findByRole('link', { name: /system logs/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/settings/system-logs');
  });

  it('hides the System Logs link for an OPERATOR user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'OPERATOR' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.queryByRole('link', { name: /system logs/i })).not.toBeInTheDocument();
  });

  it('hides the System Logs link for a REVIEWER user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'REVIEWER' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.queryByRole('link', { name: /system logs/i })).not.toBeInTheDocument();
  });

  it('hides the administration section entirely for an OPERATOR user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'OPERATOR' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.queryByRole('heading', { name: /administration/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /feedback/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /continuous learning/i })).not.toBeInTheDocument();
  });
});