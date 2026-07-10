import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Descriptions,
  Drawer,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Space,
  Table,
  Tag,
  Tooltip,
  Upload,
  message,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useState } from 'react';

import { batchDeleteMaterials, createMaterial, deleteMaterial, getMaterials, updateMaterial } from '../api/index.js';

const normFile = (event) => (Array.isArray(event) ? event : event?.fileList);

const buildFormData = (values) => {
  const formData = new FormData();
  formData.append('name', values.name);
  formData.append('material_type', values.material_type);
  formData.append('priority', values.priority ?? 0);
  if (values.remark) formData.append('remark', values.remark);
  if (values.material_type === 'contact') {
    formData.append('content', JSON.stringify({
      phone_number: values.contact_phone || '',
      first_name: values.contact_first_name || '',
      last_name: values.contact_last_name || '',
      vcard: values.contact_vcard || '',
    }));
  } else if (values.content) {
    formData.append('content', values.content);
  }
  const file = values.file?.[0]?.originFileObj;
  if (file) formData.append('file', file);
  return formData;
};

const parseContact = (content) => {
  try {
    return JSON.parse(content || '{}');
  } catch {
    return {};
  }
};

const materialTypeMeta = {
  text: { label: '文字', color: 'blue' },
  image: { label: '图片', color: 'green' },
  contact: { label: '名片', color: 'purple' },
};

export default function Materials() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [form] = Form.useForm();
  const materialType = Form.useWatch('material_type', form);

  const { data: materials = [], isLoading } = useQuery({ queryKey: ['materials'], queryFn: () => getMaterials() });

  useEffect(() => {
    form.resetFields();
    if (editing) {
      const contact = parseContact(editing.content);
      form.setFieldsValue({
        name: editing.name,
        material_type: editing.material_type,
        content: editing.content,
        contact_phone: contact.phone_number,
        contact_first_name: contact.first_name,
        contact_last_name: contact.last_name,
        contact_vcard: contact.vcard,
        priority: editing.priority,
        remark: editing.remark,
      });
    } else {
      form.setFieldsValue({ material_type: 'text', priority: 0 });
    }
  }, [editing, form, modalOpen]);

  const saveMutation = useMutation({
    mutationFn: (values) => {
      const formData = buildFormData(values);
      if (editing) return updateMaterial(editing.id, formData);
      return createMaterial(formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      setModalOpen(false);
      setEditing(null);
      message.success('素材已保存');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMaterial,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      message.success('素材已删除');
    },
  });

  const batchDeleteMutation = useMutation({
    mutationFn: batchDeleteMaterials,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      setSelectedRowKeys([]);
      message.success(`已删除 ${data.deleted} 条素材`);
    },
  });

  const columns = [
    { title: '编号', dataIndex: 'id', width: 90 },
    { title: '名称', dataIndex: 'name', width: 180 },
    {
      title: '类型',
      dataIndex: 'material_type',
      width: 100,
      render: (value) => <Tag color={materialTypeMeta[value]?.color || 'default'}>{materialTypeMeta[value]?.label || value}</Tag>,
    },
    { title: '优先级', dataIndex: 'priority', width: 100 },
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
            <Button icon={<EyeOutlined />} onClick={() => setViewing(record)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} onClick={() => { setEditing(record); setModalOpen(true); }} />
          </Tooltip>
          <Popconfirm title="确认删除该素材？" onConfirm={() => deleteMutation.mutate(record.id)}>
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
            创建素材库
          </Button>
          <Popconfirm
            title="确认批量删除选中的素材？"
            disabled={!selectedRowKeys.length}
            onConfirm={() => batchDeleteMutation.mutate(selectedRowKeys)}
          >
            <Button danger disabled={!selectedRowKeys.length} icon={<DeleteOutlined />}>批量删除</Button>
          </Popconfirm>
        </div>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={materials}
        loading={isLoading}
        rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
        scroll={{ x: 1100 }}
      />

      <Modal
        title={editing ? '编辑素材库' : '创建素材库'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
        width={680}
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={150} />
          </Form.Item>
          <Form.Item name="material_type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Radio.Group>
              <Radio value="text">文字</Radio>
              <Radio value="image">图片</Radio>
              <Radio value="contact">名片</Radio>
            </Radio.Group>
          </Form.Item>
          {materialType === 'image' ? (
            <Form.Item name="file" label="图片素材" valuePropName="fileList" getValueFromEvent={normFile} rules={[{ required: !editing, message: '请选择图片' }]}>
              <Upload accept="image/*" maxCount={1} beforeUpload={() => false} listType="picture">
                <Button>选择图片</Button>
              </Upload>
            </Form.Item>
          ) : materialType === 'contact' ? (
            <>
              <Form.Item name="contact_phone" label="名片手机号" rules={[{ required: true, message: '请输入名片手机号' }]}>
                <Input maxLength={32} placeholder="+8613800138000" />
              </Form.Item>
              <Form.Item name="contact_first_name" label="名" rules={[{ required: true, message: '请输入名' }]}>
                <Input maxLength={100} placeholder="张" />
              </Form.Item>
              <Form.Item name="contact_last_name" label="姓">
                <Input maxLength={100} placeholder="三" />
              </Form.Item>
              <Form.Item name="contact_vcard" label="扩展vCard">
                <Input.TextArea rows={3} maxLength={1000} />
              </Form.Item>
            </>
          ) : (
            <Form.Item name="content" label="文字素材内容" rules={[{ required: true, message: '请输入文字内容' }]}>
              <Input.TextArea rows={5} maxLength={5000} showCount />
            </Form.Item>
          )}
          <Form.Item name="priority" label="优先级（数字越大越靠前）">
            <InputNumber min={0} max={999999} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer title="素材详情" open={Boolean(viewing)} onClose={() => setViewing(null)} width={640}>
        {viewing ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="编号">{viewing.id}</Descriptions.Item>
              <Descriptions.Item label="名称">{viewing.name}</Descriptions.Item>
              <Descriptions.Item label="类型">{materialTypeMeta[viewing.material_type]?.label || viewing.material_type}</Descriptions.Item>
              <Descriptions.Item label="优先级">{viewing.priority}</Descriptions.Item>
              <Descriptions.Item label="备注">{viewing.remark || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewing.created_at ? dayjs(viewing.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
            </Descriptions>
            {viewing.material_type === 'image' && viewing.file_path ? <Image src={viewing.file_path} width={240} /> : null}
            {viewing.material_type === 'text' ? <Input.TextArea value={viewing.content || ''} rows={6} readOnly /> : null}
            {viewing.material_type === 'contact' ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="手机号">{parseContact(viewing.content).phone_number || '-'}</Descriptions.Item>
                <Descriptions.Item label="名">{parseContact(viewing.content).first_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="姓">{parseContact(viewing.content).last_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="vCard">{parseContact(viewing.content).vcard || '-'}</Descriptions.Item>
              </Descriptions>
            ) : null}
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
}
