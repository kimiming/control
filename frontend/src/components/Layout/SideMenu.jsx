import { MessageOutlined, PartitionOutlined, ProfileOutlined, UserOutlined } from '@ant-design/icons';
import { Menu } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';

const items = [
  { key: '/sessions', icon: <UserOutlined />, label: 'Session管理' },
  { key: '/messages', icon: <MessageOutlined />, label: '消息列表' },
  { key: '/tasks', icon: <ProfileOutlined />, label: '任务管理' },
  { key: '/proxies', icon: <PartitionOutlined />, label: '代理管理' },
];

export default function SideMenu() {
  const navigate = useNavigate();
  const location = useLocation();
  return <Menu mode="inline" selectedKeys={[location.pathname]} items={items} onClick={({ key }) => navigate(key)} />;
}
