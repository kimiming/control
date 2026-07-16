import { ClearOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, LinkOutlined, DisconnectOutlined, ImportOutlined, MoreOutlined, SafetyCertificateOutlined, SearchOutlined } from '@ant-design/icons';
import { Avatar, Button, Popconfirm, Popover, Space, Table, Tag, Tooltip, Typography } from 'antd';
import dayjs from 'dayjs';

const statusColor = {
  connected: 'green',
  connecting: 'blue',
  disconnected: 'default',
  error: 'red',
};

const statusText = {
  connected: '已连接',
  connecting: '连接中',
  disconnected: '未连接',
  error: '异常',
};

const bidirectionalColor = {
  unchecked: 'default',
  checking: 'processing',
  normal: 'green',
  blocked: 'red',
  restricted: 'red',
  unknown: 'blue',
  timeout: 'orange',
  unauthorized: 'gold',
  error: 'red',
};

const bidirectionalText = {
  unchecked: '未检测',
  checking: '检测中',
  normal: '正常（非双向号）',
  blocked: '账号已封禁',
  restricted: '疑似双向号',
  unknown: '返回文案未识别',
  timeout: '检测超时',
  unauthorized: '未授权',
  error: '检测异常',
};

const resolveAvatar = (avatar) => {
  if (!avatar) return undefined;
  if (/^https?:\/\//.test(avatar)) return avatar;
  return avatar;
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
  onTaskLogs,
  onBidirectionalCheck,
  onContactScan,
  onContactClear,
  onContactImport,
  contactOperatingSessionId,
  checkingSessionId,
  connectionOperatingSessionId,
  connectionOperatingAction,
  deletingSessionId,
}) {
  const columns = [
    {
      title: '序号',
      key: 'sequence',
      width: 80,
      render: (_, __, index) => index + 1,
    },
    {
      title: '用户',
      dataIndex: 'username',
      width: 240,
      render: (value, record) => (
        <Space>
          <Avatar src={resolveAvatar(record.avatar)}>{value?.[0]?.toUpperCase()}</Avatar>
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{value || '-'}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{record.session_name}</Typography.Text>
          </Space>
        </Space>
      ),
    },
    { title: '手机号', dataIndex: 'phone', width: 150 },
    {
      title: '分组',
      dataIndex: 'group_name',
      width: 140,
      render: (value, record) => (value ? <Tag color={record.group_color || 'blue'}>{value}</Tag> : <Tag>未分组</Tag>),
    },
    {
      title: '客服状态',
      dataIndex: 'kf_name',
      width: 140,
      render: (value, record) => (value ? <Tag color={record.kf_color || 'blue'}>{value}</Tag> : <Tag>未绑定</Tag>),
    },
    {
      title: '代理',
      dataIndex: 'proxy_name',
      width: 140,
      render: (value, record) => (value ? <Tag color={record.proxy_status === 'unreachable' ? 'red' : record.proxy_color || 'blue'}>{value}</Tag> : <Tag>未分配</Tag>),
    },
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
      render: (value) => <Tag color={statusColor[value]}>{statusText[value] || value || '-'}</Tag>,
    },
    {
      title: '双向号状态',
      dataIndex: 'bidirectional_status',
      width: 160,
      render: (value = 'unchecked', record) => (
        <Tooltip
          title={(
            <div>
              <div>{record.bidirectional_detail || '尚未进行双向号检测'}</div>
              {record.last_bidirectional_check_at ? <div>检测时间：{dayjs(record.last_bidirectional_check_at).format('YYYY-MM-DD HH:mm:ss')}</div> : null}
            </div>
          )}
        >
          <Tag color={bidirectionalColor[value] || 'default'}>{bidirectionalText[value] || value}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '已发送数量',
      dataIndex: 'sent_count',
      width: 120,
      render: (value) => value || 0,
    },
    {
      title: '通讯录数量',
      dataIndex: 'contact_count',
      width: 130,
      render: (value, record) => (
        <Tooltip title={record.contacts_scanned_at ? `识别时间：${dayjs(record.contacts_scanned_at).format('YYYY-MM-DD HH:mm:ss')}` : '尚未识别通讯录'}>
          {value == null ? <Tag color="red">未识别</Tag> : <Tag color="blue">{value}</Tag>}
        </Tooltip>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          {record.status === 'connected' ? (
            <Tooltip title="断开">
              <Button
                type="primary"
                danger
                icon={<DisconnectOutlined />}
                loading={connectionOperatingSessionId === record.id && connectionOperatingAction === 'disconnect'}
                disabled={connectionOperatingSessionId != null && connectionOperatingSessionId !== record.id}
                onClick={() => onDisconnect(record)}
              />
            </Tooltip>
          ) : (
            <Tooltip title="连接">
              <Button
                type="primary"
                icon={<LinkOutlined />}
                onClick={() => onConnect(record)}
                loading={record.status === 'connecting' || (connectionOperatingSessionId === record.id && connectionOperatingAction === 'connect')}
                disabled={connectionOperatingSessionId != null && connectionOperatingSessionId !== record.id}
              />
            </Tooltip>
          )}
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} onClick={() => onEdit(record)} />
          </Tooltip>
          <Tooltip title="任务日志">
            <Button icon={<FileTextOutlined />} onClick={() => onTaskLogs(record)} />
          </Tooltip>
          <Tooltip title="双向号测试">
            <Button
              icon={<SafetyCertificateOutlined />}
              loading={checkingSessionId === record.id || record.bidirectional_status === 'checking'}
              disabled={checkingSessionId != null && checkingSessionId !== record.id}
              onClick={() => onBidirectionalCheck(record)}
            />
          </Tooltip>
          <Popconfirm title="确认删除该Session？" onConfirm={() => onDelete(record)}>
            <Tooltip title="删除">
              <Button
                danger
                icon={<DeleteOutlined />}
                loading={deletingSessionId === record.id}
                disabled={deletingSessionId != null && deletingSessionId !== record.id}
              />
            </Tooltip>
          </Popconfirm>
          <Popover
            trigger="click"
            placement="bottomRight"
            content={(
              <Space>
                <Tooltip title="识别通讯录好友">
                  <Button icon={<SearchOutlined />} onClick={() => onContactScan(record)} />
                </Tooltip>
                <Tooltip title="清空所有通讯录">
                  <Button danger icon={<ClearOutlined />} onClick={() => onContactClear(record)} />
                </Tooltip>
                <Tooltip title="导入通讯录TXT">
                  <Button type="primary" icon={<ImportOutlined />} onClick={() => onContactImport(record)} />
                </Tooltip>
              </Space>
            )}
          >
            <Tooltip title="更多通讯录操作">
              <Button icon={<MoreOutlined />} loading={contactOperatingSessionId === record.id} />
            </Tooltip>
          </Popover>
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
      scroll={{ x: 1960 }}
    />
  );
}
