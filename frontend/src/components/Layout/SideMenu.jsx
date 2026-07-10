import { Menu } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import { menuItems } from './menuItems.jsx';

export default function SideMenu() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const items = menuItems.filter((item) => !item.rootOnly || user?.role === 'root');
  return <Menu mode="inline" selectedKeys={[location.pathname]} items={items} onClick={({ key }) => navigate(key)} />;
}
