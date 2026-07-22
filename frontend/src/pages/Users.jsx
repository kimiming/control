import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Checkbox, Form, Input, Modal, Select, Space, Table, Tag, Tooltip, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useState } from 'react';
import { createUser, getUsers, updateUser } from '../api/index.js';

const roleText = { root: 'Root', user: '普通用户' };
const defaultMenuPermissions = ['messages', 'materials'];
const menuPermissionOptions = [
  { label: '控制面板', value: 'dashboard' },
  { label: 'Session管理', value: 'sessions' },
  { label: '消息列表', value: 'messages' },
  { label: '客服管理', value: 'customers' },
  { label: '客户资料管理', value: 'customer_profiles' },
  { label: '素材库管理', value: 'materials' },
  { label: '任务管理', value: 'tasks' },
  { label: '代理管理', value: 'proxies' },
  { label: '使用文档', value: 'usage_docs' },
];

export default function Users() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const { data: users = [], isLoading } = useQuery({ queryKey: ['users'], queryFn: getUsers });
  const mutation = useMutation({
    mutationFn: (values) => {
      if (editing?.role === 'root') {
        return updateUser(editing.id, { ...values, status: editing.status || 'active' });
      }
      return editing ? updateUser(editing.id, values) : createUser(values);
    },
    onSuccess: () => {
      message.success(editing ? '用户已更新' : '用户已创建');
      setOpen(false);
      setEditing(null);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const columns = [
    { title: '编号', dataIndex: 'id', width: 90 },
    { title: '用户名', dataIndex: 'username', width: 180 },
    { title: '角色', dataIndex: 'role', width: 120, render: (value) => <Tag color={value === 'root' ? 'red' : 'blue'}>{roleText[value] || value}</Tag> },
    { title: '状态', dataIndex: 'status', width: 120, render: (value) => <Tag color={value === 'active' ? 'green' : 'default'}>{value === 'active' ? '启用' : '停用'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-') },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Tooltip title="编辑">
          <Button
            icon={<EditOutlined />}
            onClick={() => {
              setEditing(record);
              form.setFieldsValue({ username: record.username, password: '', status: record.status || 'active', menu_permissions: record.menu_permissions || defaultMenuPermissions });
              setOpen(true);
            }}
          />
        </Tooltip>
      ),
    },
  ];

  return (
    <div className="page">
      <div className="toolbar">
        <Space />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({ status: 'active', menu_permissions: defaultMenuPermissions });
            setOpen(true);
          }}
        >
          新增普通用户
        </Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={users} loading={isLoading} scroll={{ x: 900 }} />
      <Modal
        title={editing ? '编辑用户' : '新增普通用户'}
        open={open}
        onCancel={() => {
          setOpen(false);
          setEditing(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        confirmLoading={mutation.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            name="password"
            label={editing ? '新密码' : '密码'}
            rules={editing ? [] : [{ required: true, message: '请输入密码' }]}
            extra={editing ? '不填写则不修改密码' : null}
          >
            <Input.Password maxLength={100} />
          </Form.Item>
          {editing && editing.role !== 'root' ? (
            <Form.Item name="status" label="启用状态" rules={[{ required: true, message: '请选择状态' }]}>
              <Select
                options={[
                  { label: '启用', value: 'active' },
                  { label: '停用', value: 'disabled' },
                ]}
              />
            </Form.Item>
          ) : null}
          {editing?.role !== 'root' ? (
            <Form.Item name="menu_permissions" label="可查看菜单">
              <Checkbox.Group options={menuPermissionOptions} style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }} />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>
    </div>
  );
}
