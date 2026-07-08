import { DeleteOutlined, EditOutlined, LinkOutlined, DisconnectOutlined, MoreOutlined } from '@ant-design/icons';
import { Avatar, Button, Dropdown, Popconfirm, Space, Table, Tag, Tooltip } from 'antd';
import dayjs from 'dayjs';

const statusColor = {
  connected: 'green',
  connecting: 'blue',
  disconnected: 'default',
  error: 'red',
};

export default function SessionList({
  sessions,
  loading,
  selectedRowKeys,
  onSelectionChange,
  onEdit,
  onConnect,
  onDisconnect,
  onDelete,
}) {
  const columns = [
    {
      title: '用户',
      dataIndex: 'username',
      render: (value, record) => (
        <Space>
          <Avatar src={record.avatar}>{value?.[0]?.toUpperCase()}</Avatar>
          <span>{value}</span>
        </Space>
      ),
    },
    { title: '手机号', dataIndex: 'phone', width: 150 },
    { title: '分组', dataIndex: 'group_name', width: 140, render: (value) => value || '-' },
    {
      title: '登录时间',
      dataIndex: 'last_login_at',
      width: 180,
      render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '连接状态',
      dataIndex: 'status',
      width: 120,
      render: (value) => <Tag color={statusColor[value]}>{value}</Tag>,
    },
    {
      title: '健康',
      dataIndex: 'health_status',
      width: 120,
      render: (value) => value || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 210,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          {record.status === 'connected' ? (
            <Tooltip title="断开">
              <Button icon={<DisconnectOutlined />} onClick={() => onDisconnect(record)} />
            </Tooltip>
          ) : (
            <Tooltip title="连接">
              <Button icon={<LinkOutlined />} onClick={() => onConnect(record)} loading={record.status === 'connecting'} />
            </Tooltip>
          )}
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} onClick={() => onEdit(record)} />
          </Tooltip>
          <Popconfirm title="确认删除该Session？" onConfirm={() => onDelete(record)}>
            <Button danger icon={<DeleteOutlined />} />
          </Popconfirm>
          <Dropdown menu={{ items: [{ key: 'reserved', label: '扩展接口预留', disabled: true }] }}>
            <Button icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ];

  return (
    <Table
      rowKey="id"
      columns={columns}
      dataSource={sessions}
      loading={loading}
      rowSelection={{ selectedRowKeys, onChange: onSelectionChange }}
      pagination={{ pageSize: 20, showSizeChanger: true }}
      scroll={{ x: 1100 }}
    />
  );
}
