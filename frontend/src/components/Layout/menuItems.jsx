import { AppstoreOutlined, ContactsOutlined, CustomerServiceOutlined, DashboardOutlined, FileTextOutlined, MessageOutlined, PartitionOutlined, ProfileOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';

export const menuItems = [
  { key: '/dashboard', permission: 'dashboard', icon: <DashboardOutlined />, label: '控制面板' },
  { key: '/sessions', permission: 'sessions', icon: <UserOutlined />, label: 'Session管理' },
  { key: '/messages', permission: 'messages', icon: <MessageOutlined />, label: '消息列表' },
  { key: '/customers', permission: 'customers', icon: <CustomerServiceOutlined />, label: '客服管理' },
  { key: '/customer-profiles', permission: 'customer_profiles', icon: <ContactsOutlined />, label: '客户资料管理' },
  { key: '/materials', permission: 'materials', icon: <AppstoreOutlined />, label: '素材库管理' },
  { key: '/tasks', permission: 'tasks', icon: <ProfileOutlined />, label: '任务管理' },
  { key: '/proxies', permission: 'proxies', icon: <PartitionOutlined />, label: '代理管理' },
  { key: '/usage-docs', permission: 'usage_docs', icon: <FileTextOutlined />, label: '使用文档' },
  { key: '/users', icon: <TeamOutlined />, label: '用户管理', rootOnly: true },
];

export const canAccessMenu = (user, item) => {
  if (!user) return false;
  if (item.rootOnly) return user.role === 'root';
  return user.role === 'root' || user.menu_permissions?.includes(item.permission);
};

export const firstAccessiblePath = (user) => menuItems.find((item) => canAccessMenu(user, item))?.key || '/404';
