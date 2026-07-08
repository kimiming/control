import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import MainLayout from './components/Layout/MainLayout.jsx';
import Sessions from './pages/Sessions.jsx';
import Messages from './pages/Messages.jsx';
import Tasks from './pages/Tasks.jsx';
import Proxies from './pages/Proxies.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <MainLayout>
        <Routes>
          <Route path="/" element={<Navigate to="/sessions" replace />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/proxies" element={<Proxies />} />
        </Routes>
      </MainLayout>
    </BrowserRouter>
  );
}
