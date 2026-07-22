import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Spin } from 'antd';
import { lazy, Suspense } from 'react';
import { AuthProvider, useAuth } from './auth/AuthContext.jsx';
import MainLayout from './components/Layout/MainLayout.jsx';
import Sessions from './pages/Sessions.jsx';
import Messages from './pages/Messages.jsx';
import Tasks from './pages/Tasks.jsx';
import Proxies from './pages/Proxies.jsx';
import Materials from './pages/Materials.jsx';
import Customers from './pages/Customers.jsx';
import CustomerProfiles from './pages/CustomerProfiles.jsx';
import Login from './pages/Login.jsx';
import UsageDocs from './pages/UsageDocs.jsx';
import Users from './pages/Users.jsx';
import VerificationCode from './pages/VerificationCode.jsx';

const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));

function ProtectedApp() {
  const auth = useAuth();
  if (auth.loading) return <Spin fullscreen />;
  if (!auth.token || !auth.user) return <Navigate to="/login" replace />;

  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Suspense fallback={<Spin fullscreen />}><Dashboard /></Suspense>} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/usage-docs" element={<UsageDocs />} />
        <Route path="/messages" element={<Messages />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/materials" element={<Materials />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/customer-profiles" element={<CustomerProfiles />} />
        <Route path="/proxies" element={<Proxies />} />
        <Route path="/users" element={auth.user.role === 'root' ? <Users /> : <Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </MainLayout>
  );
}

function ProtectedVerificationCode() {
  const auth = useAuth();
  if (auth.loading) return <Spin fullscreen />;
  if (!auth.token || !auth.user) return <Navigate to="/login" replace />;
  return <VerificationCode />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/sessions/:sessionId/verification-code" element={<ProtectedVerificationCode />} />
          <Route path="/*" element={<ProtectedApp />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
