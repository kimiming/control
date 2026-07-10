import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import {
  createSupportAgent,
  deleteSupportAgent,
  getGroups,
  getSupportAgents,
  updateSupportAgent,
} from '../api/index.js';

const tagColorOptions = [
  { label: '红', value: 'red' },
  { label: '橙', value: 'orange' },
  { label: '黄', value: 'yellow' },
  { label: '绿', value: 'green' },
  { label: '蓝', value: 'blue' },
  { label: '靛', value: 'geekblue' },
  { label: '紫', value: 'purple' },
];

const agentStatusText = {
  active: '启用',
  disabled: '停用',
};

export default function Customers() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const { data: agents = [], isLoading } = useQuery({
    queryKey: ['support-agents'],
    queryFn: getSupportAgents,
  });

  const { data: groups = [] } = useQuery({
    queryKey: ['session-groups', 'support-agent-bind'],
    queryFn: getGroups,
  });

  const groupOptions = useMemo(
    () => [
      ...groups.map((item) => ({ label: item.name, value: item.id, color: item.color })),
      { label: '未分组Session', value: 0, color: undefined },
    ],
    [groups],
  );

  const saveMutation = useMutation({
    mutationFn: (values) => (editing ? updateSupportAgent(editing.id, values) : createSupportAgent(values)),
    onSuccess: () => {
      message.success(editing ? '客服已更新' : '客服已新增');
      setModalOpen(false);
      setEditing(null);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['support-agents'] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSupportAgent,
    onSuccess: () => {
      message.success('客服已删除');
      queryClient.invalidateQueries({ queryKey: ['support-agents'] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ status: 'active', color: 'blue', group_ids: [] });
    setModalOpen(true);
  };

  const openEdit = (record) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      remark: record.remark,
      color: record.color || 'blue',
      status: record.status || 'active',
      group_ids: Array.from(new Set((record.sessions || []).map((item) => item.group_id || 0))),
    });
    setModalOpen(true);
  };

  const renderGroupTag = ({ label, value, closable, onClose }) => {
    const group = groupOptions.find((item) => item.value === value);
    return (
      <Tag
        color={group?.color}
        closable={closable}
        onClose={onClose}
        style={{ marginInlineEnd: 4 }}
      >
        {label}
      </Tag>
    );
  };

  const renderGroupOption = (option) => {
    const group = groupOptions.find((item) => item.value === option.value);
    return <Tag color={group?.color}>{option.label}</Tag>;
  };

  const getSessionGroups = (sessions = []) => (
    Array.from(
      new Map(sessions.map((item) => {
        const groupId = item.group_id || 0;
        const group = groupOptions.find((option) => option.value === groupId);
        return [groupId, { id: groupId, name: item.group_name || '未分组Session', color: group?.color }];
      })).values(),
    )
  );

  const renderGroupTags = (sessionGroups) => (
    <Space wrap size={[4, 4]}>
      {sessionGroups.map((group) => <Tag key={group.id} color={group.color}>{group.name}</Tag>)}
    </Space>
  );

  const renderGroups = (sessions = []) => {
    if (!sessions.length) return <Tag>未绑定</Tag>;
    const sessionGroups = getSessionGroups(sessions);
    const visibleGroups = sessionGroups.slice(0, 3);
    return (
      <Tooltip title={renderGroupTags(sessionGroups)} color="#fff" overlayInnerStyle={{ color: '#1f2328' }}>
        <div className="customer-group-cell">
          {visibleGroups.map((group) => <Tag key={group.id} color={group.color}>{group.name}</Tag>)}
          {sessionGroups.length > visibleGroups.length ? <Tag>...</Tag> : null}
        </div>
      </Tooltip>
    );
  };

  const columns = [
    { title: '编号', dataIndex: 'id', width: 80 },
    { title: '客服名称', dataIndex: 'name', width: 150, ellipsis: true, render: (value, record) => <Tag color={record.color || 'blue'}>{value}</Tag> },
    {
      title: '绑定分组',
      dataIndex: 'sessions',
      width: 240,
      render: renderGroups,
    },
    { title: '绑定数量', dataIndex: 'session_count', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value) => <Tag color={value === 'active' ? 'green' : 'default'}>{agentStatusText[value] || value || '-'}</Tag>,
    },
    {
      title: '备注',
      dataIndex: 'remark',
      width: 220,
      ellipsis: true,
      render: (value) => value ? (
        <Tooltip title={value}>
          <span className="table-ellipsis-text">{value}</span>
        </Tooltip>
      ) : '-',
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-') },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} onClick={() => openEdit(record)} />
          </Tooltip>
          <Popconfirm title="确认删除该客服？绑定的Session会变为未绑定" onConfirm={() => deleteMutation.mutate(record.id)}>
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
        <Typography.Title level={4} style={{ margin: 0 }}>客服管理</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增客服</Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={agents}
        loading={isLoading}
        pagination={{ pageSize: 20 }}
        tableLayout="fixed"
        scroll={{ x: 1210 }}
      />

      <Modal
        title={editing ? '编辑客服' : '新增客服'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Form.Item name="name" label="客服名称" rules={[{ required: true, message: '请输入客服名称' }]}>
            <Input placeholder="例如：客服1" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { label: '启用', value: 'active' },
                { label: '停用', value: 'disabled' },
              ]}
            />
          </Form.Item>
          <Form.Item name="color" label="Tag颜色" initialValue="blue">
            <Select
              options={tagColorOptions.map((item) => ({
                value: item.value,
                label: (
                  <Space>
                    <Tag color={item.value}>{item.label}</Tag>
                    <span>{item.label}</span>
                  </Space>
                ),
              }))}
            />
          </Form.Item>
          <Form.Item name="group_ids" label="绑定Session分组">
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="选择分组后，后端会自动绑定该分组下所有Session"
              options={groupOptions}
              optionRender={renderGroupOption}
              tagRender={renderGroupTag}
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
