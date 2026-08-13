import { Navigate, Route, Routes } from 'react-router-dom';

import ProtectedLayout from '../components/layout/ProtectedLayout/ProtectedLayout';
import { ADMIN_NAV_ITEMS, INTERNAL_ROUTES, NAV_ITEMS } from '../data/navigation';
import ApplicationDetailsPage from '../pages/ApplicationDetails/ApplicationDetailsPage';
import ApplicationsPage from '../pages/Applications/ApplicationsPage';
import CreateApplicationPage from '../pages/CreateApplication/CreateApplicationPage';
import Dashboard from '../pages/Dashboard/Dashboard';
import HumanReviewPage from '../pages/HumanReview/HumanReviewPage';
import LoginPage from '../pages/Login/LoginPage';
import OperatorDashboardPage from '../pages/OperatorDashboard/OperatorDashboardPage';
import PlaceholderPage from '../pages/Placeholder/PlaceholderPage';
import ProcessingPage from '../pages/Processing/ProcessingPage';
import SettingsPage from '../pages/Settings/SettingsPage';
import UploadDocumentsPage from '../pages/UploadDocuments/UploadDocumentsPage';
import ValidationReportPage from '../pages/ValidationReport/ValidationReportPage';
import VerificationPage from '../pages/Verification/VerificationPage';

/**
 * Application route table.
 *
 * The applications module owns the list, create, details and upload pages.
 * The Validation Report and Human Review pages are real operator workflows;
 * the validation task queue (shipped previously at /human-review) stays
 * reachable at /validation-tasks but is not exposed in the sidebar. Every
 * other sidebar entry resolves to the shared PlaceholderPage so no path
 * returns a 404 and the sidebar active state matches the route. Internal
 * processing routes stay reachable as placeholders but are not exposed in the
 * sidebar. Admin-only routes (Feedback, Continuous Learning) are not sidebar
 * entries either; they are reached from the Settings page. Unknown URLs are
 * redirected to the dashboard.
 */
const PLACEHOLDER_ITEMS = [
  ...NAV_ITEMS.filter(
    ({ id }) =>
      !['dashboard', 'applications', 'processing', 'settings', 'human-review', 'reports'].includes(id)
  ),
  ...ADMIN_NAV_ITEMS,
  ...INTERNAL_ROUTES,
];

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<ProtectedLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="applications" element={<ApplicationsPage />} />
        <Route path="applications/new" element={<CreateApplicationPage />} />
        <Route path="applications/:applicationId/upload" element={<UploadDocumentsPage />} />
        <Route path="applications/:applicationId/verification" element={<VerificationPage />} />
        <Route path="applications/:applicationId" element={<ApplicationDetailsPage />} />
        <Route path="processing" element={<ProcessingPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="reports" element={<ValidationReportPage />} />
        <Route path="human-review" element={<HumanReviewPage />} />
        <Route path="validation-tasks" element={<OperatorDashboardPage />} />
        {PLACEHOLDER_ITEMS.map(({ id, label, path }) => (
          <Route
            key={id}
            path={path}
            element={
              <PlaceholderPage
                title={label}
                description={`The ${label} module is coming in a future phase.`}
              />
            }
          />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
