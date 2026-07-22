import { DeleteOutlined, EditOutlined, PlusOutlined, CheckCircleOutlined, ExperimentOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Radio, Select, Space, Table, Tag, Tooltip, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { activateProxy, createProxy, deleteProxy, getGroups, getProxies, testProxy, updateProxy } from '../api/index.js';

const proxyStatusText = {
  reachable: '可连接',
  unreachable: '不可连接',
};

const tagColorOptions = [
  { label: '红', value: 'red' },
  { label: '橙', value: 'orange' },
  { label: '黄', value: 'yellow' },
  { label: '绿', value: 'green' },
  { label: '蓝', value: 'blue' },
  { label: '靛', value: 'geekblue' },
  { label: '紫', value: 'purple' },
];

export default function Proxies() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form] = Form.useForm();
  const { data: proxies = [], isLoading } = useQuery({ queryKey: ['proxies'], queryFn: getProxies });
  const { data: groups = [] } = useQuery({ queryKey: ['session-groups'], queryFn: getGroups });

  const groupOptions = useMemo(
    () => [
      { value: 0, label: '未分组' },
      ...groups.map((group) => ({ value: group.id, label: group.name, color: group.color })),
    ],
    [groups],
  );

  const renderGroupOption = (option) => {
    if (option.value === 0) return <Tag>未分组</Tag>;
    const group = groups.find((item) => item.id === option.value);
    return <Tag color={group?.color || 'blue'}>{option.label}</Tag>;
  };

  const renderGroupTag = ({ label, value, closable, onClose }) => {
    const group = groups.find((item) => item.id === value);
    return (
      <Tag
        color={value === 0 ? undefined : group?.color || 'blue'}
        closable={closable}
        onClose={onClose}
        style={{ marginInlineEnd: 4 }}
      >
        {label}
      </Tag>
    );
  };

  useEffect(() => {
    form.resetFields();
    if (editing) {
      form.setFieldsValue(editing);
    } else {
      form.setFieldsValue({ scheme: 'http', color: 'blue', is_active: false, group_ids: [] });
    }
  }, [editing, form, modalOpen]);

  const saveMutation = useMutation({
    mutationFn: (values) => (editing ? updateProxy(editing.id, values) : createProxy(values)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proxies'] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      setModalOpen(false);
      setEditing(null);
      message.success('代理已保存');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProxy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proxies'] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      message.success('代理已删除');
    },
  });

  const activateMutation = useMutation({
    mutationFn: activateProxy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proxies'] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      message.success('代理状态已更新');
    },
  });

  const testMutation = useMutation({
    mutationFn: testProxy,
    onSuccess: (proxy) => {
      queryClient.invalidateQueries({ queryKey: ['proxies'] });
      if (proxy.status === 'reachable') {
        message.success('代理认证成功，且可连接Telegram');
      } else {
        message.error(proxy.error_message || '代理不可连接');
      }
    },
  });

  const columns = [
    { title: '名称', dataIndex: 'name', render: (value, record) => <Tag color={record.color || 'blue'}>{value}</Tag> },
    {
      title: '地址',
      key: 'address',
      render: (_, record) => `${record.scheme}://${record.host}:${record.port}`,
    },
    {
      title: '认证',
      dataIndex: 'username',
      width: 100,
      render: (value) => (value ? '已配置' : '-'),
    },
    {
      title: '绑定分组',
      dataIndex: 'bound_group_ids',
      width: 220,
      render: (value = []) => value.length ? (
        <Space wrap>
          {value.map((groupId) => {
            const option = groupOptions.find((item) => item.value === groupId);
            return <Tag key={groupId} color={option?.color || undefined}>{option?.label || groupId}</Tag>;
          })}
        </Space>
      ) : <Tag>未分配</Tag>,
    },
    {
      title: '状态',
      key: 'status',
      width: 160,
      render: (_, record) => (
        <Space>
          {record.is_active ? <Tag color="green">启用中</Tag> : <Tag>未启用</Tag>}
          {record.status ? <Tag color={record.status === 'reachable' ? 'blue' : 'red'}>{proxyStatusText[record.status] || record.status}</Tag> : null}
        </Space>
      ),
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (value) => value || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_, record) => (
        <Space>
          <Tooltip title={record.is_active ? '停用' : '启用'}>
            <Button icon={<CheckCircleOutlined />} onClick={() => activateMutation.mutate(record.id)} />
          </Tooltip>
          <Tooltip title="测试">
            <Button icon={<ExperimentOutlined />} onClick={() => testMutation.mutate(record.id)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} onClick={() => { setEditing(record); setModalOpen(true); }} />
          </Tooltip>
          <Popconfirm title="确认删除该代理？" onConfirm={() => deleteMutation.mutate(record.id)}>
            <Tooltip title="删除">
              <Button danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page">
      <div className="toolbar">
        <div className="toolbar-left">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setModalOpen(true); }}>
            添加代理
          </Button>
        </div>
      </div>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={proxies} pagination={{ pageSize: 20 }} scroll={{ x: 1100 }} />

      <Modal
        title={editing ? '编辑代理' : '添加代理'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={100} placeholder="本地代理" />
          </Form.Item>
          <Form.Item name="scheme" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select
              options={[
                { value: 'http', label: 'HTTP' },
                { value: 'https', label: 'HTTPS' },
                { value: 'socks5', label: 'SOCKS5' },
                { value: 'socks4', label: 'SOCKS4' },
              ]}
            />
          </Form.Item>
          <Form.Item name="host" label="主机" rules={[{ required: true, message: '请输入主机' }]}>
            <Input maxLength={255} placeholder="192.168.1.18" />
          </Form.Item>
          <Form.Item name="port" label="端口" rules={[{ required: true, message: '请输入端口' }]}>
            <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="10808" />
          </Form.Item>
          <Form.Item name="username" label="用户名">
            <Input maxLength={150} />
          </Form.Item>
          <Form.Item name="password" label="密码">
            <Input.Password maxLength={255} />
          </Form.Item>
          <Form.Item name="color" label="Tag颜色" initialValue="blue">
            <Radio.Group>
              <Space wrap>
                {tagColorOptions.map((item) => (
                  <Radio key={item.value} value={item.value}>
                    <Tag color={item.value}>{item.label}</Tag>
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="group_ids" label="分配给Session分组">
            <Select
              mode="multiple"
              allowClear
              placeholder="不选则不会自动分配给任何Session"
              options={groupOptions}
              optionRender={renderGroupOption}
              tagRender={renderGroupTag}
            />
          </Form.Item>
          <Form.Item name="is_active" label="保存后启用">
            <Select
              options={[
                { value: false, label: '否' },
                { value: true, label: '是' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
