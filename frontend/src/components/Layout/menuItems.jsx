import { AppstoreOutlined, ContactsOutlined, CustomerServiceOutlined, DashboardOutlined, FileTextOutlined, MessageOutlined, PartitionOutlined, ProfileOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';

export const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '控制面板' },
  { key: '/sessions', icon: <UserOutlined />, label: 'Session管理' },
  { key: '/messages', icon: <MessageOutlined />, label: '消息列表' },
  { key: '/customers', icon: <CustomerServiceOutlined />, label: '客服管理' },
  { key: '/customer-profiles', icon: <ContactsOutlined />, label: '客户资料管理' },
  { key: '/materials', icon: <AppstoreOutlined />, label: '素材库管理' },
  { key: '/tasks', icon: <ProfileOutlined />, label: '任务管理' },
  { key: '/proxies', icon: <PartitionOutlined />, label: '代理管理' },
  { key: '/usage-docs', icon: <FileTextOutlined />, label: '使用文档' },
  { key: '/users', icon: <TeamOutlined />, label: '用户管理', rootOnly: true },
];
