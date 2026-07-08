import { Layout, Typography } from 'antd';
import SideMenu from './SideMenu.jsx';

const { Header, Sider, Content } = Layout;

export default function MainLayout({ children }) {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="light">
        <div style={{ height: 56, display: 'flex', alignItems: 'center', padding: '0 16px' }}>
          <Typography.Title level={4} style={{ margin: 0 }}>TG运营管理</Typography.Title>
        </div>
        <SideMenu />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 20px', borderBottom: '1px solid #edf0f3' }}>
          <Typography.Text strong>营销管理控制台</Typography.Text>
        </Header>
        <Content>{children}</Content>
      </Layout>
    </Layout>
  );
}
