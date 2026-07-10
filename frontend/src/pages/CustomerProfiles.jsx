import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Drawer, Form, Input, Modal, Popconfirm, Space, Table, Tooltip, Upload, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useState } from 'react';

import {
  createCustomerProfile,
  deleteCustomerProfile,
  getCustomerProfile,
  getCustomerProfiles,
  updateCustomerProfile,
} from '../api/index.js';

const normFile = (event) => (Array.isArray(event) ? event : event?.fileList);

const buildFormData = (values) => {
  const formData = new FormData();
  formData.append('name', values.name);
  if (values.remark) formData.append('remark', values.remark);
  const file = values.file?.[0]?.originFileObj;
  if (file) formData.append('file', file);
  return formData;
};

export default function CustomerProfiles() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewingId, setViewingId] = useState(null);
  const [form] = Form.useForm();

  const { data: profiles = [], isLoading } = useQuery({ queryKey: ['customer-profiles'], queryFn: getCustomerProfiles });
  const { data: viewing } = useQuery({
    queryKey: ['customer-profile', viewingId],
    queryFn: () => getCustomerProfile(viewingId),
    enabled: Boolean(viewingId),
  });

  useEffect(() => {
    form.resetFields();
    if (editing) {
      form.setFieldsValue({ name: editing.name, remark: editing.remark });
    }
  }, [editing, form, modalOpen]);

  const saveMutation = useMutation({
    mutationFn: (values) => {
      const formData = buildFormData(values);
      if (editing) return updateCustomerProfile(editing.id, formData);
      return createCustomerProfile(formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customer-profiles'] });
      setModalOpen(false);
      setEditing(null);
      message.success('客户资料已保存');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCustomerProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customer-profiles'] });
      message.success('客户资料已删除');
    },
  });

  const columns = [
    { title: '编号', dataIndex: 'id', width: 90 },
    { title: '名称', dataIndex: 'name', width: 220 },
    { title: '号码数量', dataIndex: 'total_count', width: 120 },
    { title: '备注', dataIndex: 'remark', ellipsis: true, render: (value) => value || '-' },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Tooltip title="查看">
            <Button icon={<EyeOutlined />} onClick={() => setViewingId(record.id)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} onClick={() => { setEditing(record); setModalOpen(true); }} />
          </Tooltip>
          <Popconfirm title="确认删除该客户资料？" onConfirm={() => deleteMutation.mutate(record.id)}>
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
            创建客户资料
          </Button>
        </div>
      </div>

      <Table rowKey="id" columns={columns} dataSource={profiles} loading={isLoading} scroll={{ x: 1000 }} />

      <Modal
        title={editing ? '编辑客户资料' : '创建客户资料'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={150} />
          </Form.Item>
          <Form.Item
            name="file"
            label="客户手机号TXT"
            valuePropName="fileList"
            getValueFromEvent={normFile}
            rules={[{ required: !editing, message: '请上传TXT文件' }]}
          >
            <Upload accept=".txt" maxCount={1} beforeUpload={() => false}>
              <Button>选择TXT</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer title="客户资料详情" open={Boolean(viewingId)} onClose={() => setViewingId(null)} width={640}>
        {viewing ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Input value={viewing.name} readOnly />
            <Input value={`号码数量：${viewing.total_count}`} readOnly />
            <Input.TextArea value={viewing.content || ''} rows={18} readOnly />
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
}
