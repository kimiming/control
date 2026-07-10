import { Avatar, Button, Layout, Space, Typography } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import { menuItems } from './menuItems.jsx';
import SideMenu from './SideMenu.jsx';

const { Header, Sider, Content } = Layout;

const avatarColors = ['#1677ff', '#13c2c2', '#52c41a', '#faad14', '#fa8c16', '#f5222d', '#722ed1', '#eb2f96'];

const userAvatarColor = (username = '') => {
  const code = (username[0] || 'A').toUpperCase().charCodeAt(0);
  return avatarColors[Math.max(code - 65, 0) % avatarColors.length];
};

export default function MainLayout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const auth = useAuth();
  const currentTitle = menuItems.find((item) => item.key === location.pathname)?.label || '营销管理控制台';

  const logout = () => {
    auth.logout();
    navigate('/login', { replace: true });
  };

  return (
    <Layout className="app-shell">
      <Sider width={220} theme="light">
        <div className="brand-bar">
          <Typography.Title level={4} style={{ margin: 0 }}>TG运营管理</Typography.Title>
        </div>
        <SideMenu />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Typography.Text strong>{currentTitle}</Typography.Text>
          <Space size={12}>
            <Avatar style={{ background: userAvatarColor(auth.user?.username) }}>
              {(auth.user?.username?.[0] || 'U').toUpperCase()}
            </Avatar>
            <Typography.Text strong>{auth.user?.username}</Typography.Text>
            <Button onClick={logout}>退出</Button>
          </Space>
        </Header>
        <Content>{children}</Content>
      </Layout>
    </Layout>
  );
}
