import SessionTimeoutModal from '../../auth/SessionTimeoutModal/SessionTimeoutModal';
import ProtectedRoute from '../../../auth/ProtectedRoute';
import DashboardLayout from '../DashboardLayout/DashboardLayout';
import { ApplicationsProvider } from '../../../store/ApplicationsContext';

function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <ApplicationsProvider>
        <DashboardLayout />
        <SessionTimeoutModal />
      </ApplicationsProvider>
    </ProtectedRoute>
  );
}

export default ProtectedLayout;
