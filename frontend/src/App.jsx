import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Button, Result, Spin } from 'antd';
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
import { canAccessMenu, firstAccessiblePath, menuItems } from './components/Layout/menuItems.jsx';

const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));

function NotFound() {
  const auth = useAuth();
  return <Result status="404" title="404" subTitle="页面不存在或你没有访问权限" extra={<Button type="primary" href={firstAccessiblePath(auth.user)}>返回可用页面</Button>} />;
}

function MenuRoute({ path, children }) {
  const { user } = useAuth();
  const item = menuItems.find((entry) => entry.key === path);
  return canAccessMenu(user, item) ? children : <NotFound />;
}

function ProtectedApp() {
  const auth = useAuth();
  if (auth.loading) return <Spin fullscreen />;
  if (!auth.token || !auth.user) return <Navigate to="/login" replace />;

  return (
    <MainLayout>
      <Routes>
        <Route path="/" element={<Navigate to={firstAccessiblePath(auth.user)} replace />} />
        <Route path="/dashboard" element={<MenuRoute path="/dashboard"><Suspense fallback={<Spin fullscreen />}><Dashboard /></Suspense></MenuRoute>} />
        <Route path="/sessions" element={<MenuRoute path="/sessions"><Sessions /></MenuRoute>} />
        <Route path="/usage-docs" element={<MenuRoute path="/usage-docs"><UsageDocs /></MenuRoute>} />
        <Route path="/messages" element={<MenuRoute path="/messages"><Messages /></MenuRoute>} />
        <Route path="/tasks" element={<MenuRoute path="/tasks"><Tasks /></MenuRoute>} />
        <Route path="/materials" element={<MenuRoute path="/materials"><Materials /></MenuRoute>} />
        <Route path="/customers" element={<MenuRoute path="/customers"><Customers /></MenuRoute>} />
        <Route path="/customer-profiles" element={<MenuRoute path="/customer-profiles"><CustomerProfiles /></MenuRoute>} />
        <Route path="/proxies" element={<MenuRoute path="/proxies"><Proxies /></MenuRoute>} />
        <Route path="/users" element={<MenuRoute path="/users"><Users /></MenuRoute>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </MainLayout>
  );
}

function ProtectedVerificationCode() {
  const auth = useAuth();
  if (auth.loading) return <Spin fullscreen />;
  if (!auth.token || !auth.user) return <Navigate to="/login" replace />;
  const item = menuItems.find((entry) => entry.key === '/sessions');
  return canAccessMenu(auth.user, item) ? <VerificationCode /> : <NotFound />;
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
