import { DeleteOutlined, EditOutlined, EyeOutlined, ImportOutlined, PlusOutlined } from '@ant-design/icons';
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
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Upload,
  message,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useMemo, useState } from 'react';

import {
  batchDeleteMaterials,
  batchMoveMaterials,
  createMaterial,
  createMaterialGroup,
  deleteMaterial,
  deleteMaterialGroup,
  getMaterialGroups,
  getMaterials,
  importTextMaterials,
  importImageMaterials,
  updateMaterial,
  updateMaterialGroup,
} from '../api/index.js';

const normFile = (event) => (Array.isArray(event) ? event : event?.fileList);

const buildFormData = (values) => {
  const formData = new FormData();
  formData.append('name', values.name);
  formData.append('material_type', values.material_type);
  formData.append('priority', values.priority ?? 0);
  if (values.group_id !== undefined && values.group_id !== null) formData.append('group_id', values.group_id);
  if (values.remark) formData.append('remark', values.remark);
  if (values.material_type === 'contact') {
    formData.append('content', JSON.stringify({
      phone_number: values.contact_phone || '',
      username: values.contact_username || '',
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

const groupColorOptions = [
  { label: '红', value: 'red' },
  { label: '橙', value: 'orange' },
  { label: '黄', value: 'yellow' },
  { label: '绿', value: 'green' },
  { label: '蓝', value: 'blue' },
  { label: '靛', value: 'geekblue' },
  { label: '紫', value: 'purple' },
];

export default function Materials() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [groupEditorOpen, setGroupEditorOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveGroupId, setMoveGroupId] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [imageImportOpen, setImageImportOpen] = useState(false);
  const [filters, setFilters] = useState({});
  const [searchKeyword, setSearchKeyword] = useState('');
  const [form] = Form.useForm();
  const [groupForm] = Form.useForm();
  const [importForm] = Form.useForm();
  const [imageImportForm] = Form.useForm();
  const materialType = Form.useWatch('material_type', form);

  const { data: materials = [], isLoading } = useQuery({
    queryKey: ['materials', filters],
    queryFn: () => getMaterials(filters),
  });
  const { data: materialGroups = [] } = useQuery({ queryKey: ['material-groups'], queryFn: getMaterialGroups });
  const groupMap = useMemo(() => new Map(materialGroups.map((group) => [group.id, group])), [materialGroups]);

  const renderGroupTag = (groupId) => {
    if (!groupId) return <Tag>未分组</Tag>;
    const group = groupMap.get(groupId);
    return group ? <Tag color={group.color || 'blue'}>{group.name}</Tag> : <Tag>分组已删除</Tag>;
  };

  const renderGroupOption = (option) => {
    const group = groupMap.get(option.value);
    return group ? <Tag color={group.color || 'blue'}>{group.name}</Tag> : option.label;
  };

  const resetFilters = () => {
    setSearchKeyword('');
    setFilters({});
    setSelectedRowKeys([]);
  };

  useEffect(() => {
    form.resetFields();
    if (editing) {
      const contact = parseContact(editing.content);
      form.setFieldsValue({
        name: editing.name,
        material_type: editing.material_type,
        content: editing.content,
        contact_phone: contact.phone_number,
        contact_username: contact.username,
        contact_first_name: contact.first_name,
        contact_last_name: contact.last_name,
        contact_vcard: contact.vcard,
        priority: editing.priority,
        group_id: editing.group_id,
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
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
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
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      message.success('素材已删除');
    },
  });

  const batchDeleteMutation = useMutation({
    mutationFn: batchDeleteMaterials,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      setSelectedRowKeys([]);
      message.success(`已删除 ${data.deleted} 条素材`);
    },
  });

  const saveGroupMutation = useMutation({
    mutationFn: (values) => (editingGroup ? updateMaterialGroup(editingGroup.id, values) : createMaterialGroup(values)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      setGroupEditorOpen(false);
      setEditingGroup(null);
      message.success('分组已保存');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const deleteGroupMutation = useMutation({
    mutationFn: deleteMaterialGroup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      message.success('分组已删除，原素材已移至未分组');
    },
  });

  const moveMutation = useMutation({
    mutationFn: () => batchMoveMaterials(selectedRowKeys, moveGroupId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      setSelectedRowKeys([]);
      setMoveOpen(false);
      message.success(`已转移 ${data.moved} 条素材`);
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const importMutation = useMutation({
    mutationFn: (values) => {
      const formData = new FormData();
      formData.append('file', values.file[0].originFileObj);
      if (values.group_id !== undefined && values.group_id !== null) formData.append('group_id', values.group_id);
      if (values.delimiter?.trim()) formData.append('delimiter', values.delimiter.trim());
      return importTextMaterials(formData);
    },
    onSuccess: (data, values) => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      setImportOpen(false);
      importForm.resetFields();
      const skippedLabel = values.delimiter?.trim() ? '个空白片段' : '个空行';
      message.success(`导入完成：已创建 ${data.created} 条文字素材，跳过 ${data.skipped} ${skippedLabel}`);
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message || '导入失败'),
  });

  const imageImportMutation = useMutation({
    mutationFn: (values) => {
      const formData = new FormData();
      values.files.forEach((item) => {
        const file = item.originFileObj;
        formData.append('files', file, file.webkitRelativePath || file.name);
      });
      if (values.group_id !== undefined && values.group_id !== null) formData.append('group_id', values.group_id);
      return importImageMaterials(formData);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['materials'] });
      queryClient.invalidateQueries({ queryKey: ['material-groups'] });
      setImageImportOpen(false);
      imageImportForm.resetFields();
      const text = `导入完成：已创建 ${data.created} 条图片素材${data.skipped ? `，跳过 ${data.skipped} 个无效文件` : ''}`;
      if (data.skipped) message.warning(text, 8); else message.success(text);
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message || '批量导入图片失败'),
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
    {
      title: '所属分组',
      dataIndex: 'group_id',
      width: 150,
      render: (value) => renderGroupTag(value),
    },
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
          <Button icon={<ImportOutlined />} onClick={() => { importForm.resetFields(); setImportOpen(true); }}>
            导入TXT创建文字素材
          </Button>
          <Button icon={<ImportOutlined />} onClick={() => { imageImportForm.resetFields(); setImageImportOpen(true); }}>
            批量导入创建图片素材
          </Button>
          <Button onClick={() => setGroupsOpen(true)}>分组管理</Button>
          <Button disabled={!selectedRowKeys.length} onClick={() => { setMoveGroupId(null); setMoveOpen(true); }}>批量转移分组</Button>
          <Popconfirm
            title="确认批量删除选中的素材？"
            disabled={!selectedRowKeys.length}
            onConfirm={() => batchDeleteMutation.mutate(selectedRowKeys)}
          >
            <Button danger disabled={!selectedRowKeys.length} icon={<DeleteOutlined />}>批量删除</Button>
          </Popconfirm>
        </div>
        <div className="toolbar-right">
          <Input.Search
            allowClear
            value={searchKeyword}
            placeholder="搜索素材名称、内容或备注"
            style={{ width: 260 }}
            onChange={(event) => {
              const value = event.target.value;
              setSearchKeyword(value);
              if (!value) {
                setFilters((current) => ({ ...current, keyword: undefined }));
                setSelectedRowKeys([]);
              }
            }}
            onSearch={(value) => {
              setFilters((current) => ({ ...current, keyword: value.trim() || undefined }));
              setSelectedRowKeys([]);
            }}
          />
          <Select
            allowClear
            placeholder="素材类型"
            style={{ width: 130 }}
            value={filters.material_type}
            options={Object.entries(materialTypeMeta).map(([value, meta]) => ({ value, label: meta.label }))}
            onChange={(value) => {
              setFilters((current) => ({ ...current, material_type: value }));
              setSelectedRowKeys([]);
            }}
          />
          <Select
            allowClear
            placeholder="所属分组"
            style={{ width: 160 }}
            value={filters.group_id}
            options={[
              { value: 0, label: '未分组' },
              ...materialGroups.map((group) => ({ value: group.id, label: group.name })),
            ]}
            optionRender={renderGroupOption}
            onChange={(value) => {
              setFilters((current) => ({ ...current, group_id: value }));
              setSelectedRowKeys([]);
            }}
          />
          <Button onClick={resetFilters}>重置筛选</Button>
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
              <Form.Item
                name="contact_username"
                label="Telegram 用户名"
                extra="填写后，发送名片时会同时发送可点击的聊天链接"
                rules={[{
                  pattern: /^@?[A-Za-z0-9_]{3,32}$/,
                  message: '请输入 3-32 位 Telegram 用户名，可带 @',
                }]}
              >
                <Input maxLength={33} placeholder="@username" />
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
          <Form.Item name="group_id" label="所属分组">
            <Select
              allowClear
              placeholder="可暂不分组"
              options={materialGroups.map((group) => ({ value: group.id, label: group.name }))}
              optionRender={renderGroupOption}
              labelRender={renderGroupOption}
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="批量导入创建图片素材"
        open={imageImportOpen}
        onCancel={() => setImageImportOpen(false)}
        onOk={() => imageImportForm.submit()}
        confirmLoading={imageImportMutation.isPending}
        destroyOnClose
        width={620}
      >
        <Form form={imageImportForm} layout="vertical" onFinish={(values) => imageImportMutation.mutate(values)}>
          <Form.Item
            name="files"
            label="选择图片文件夹"
            valuePropName="fileList"
            getValueFromEvent={normFile}
            extra="选择一个文件夹后，将识别其中所有图片；每张有效图片创建为一条图片素材。单次最多200张，每张不超过20MB。"
            rules={[{ required: true, message: '请选择包含图片的文件夹' }]}
          >
            <Upload directory multiple accept="image/*" beforeUpload={() => false} listType="picture" maxCount={200}>
              <Button icon={<ImportOutlined />}>选择图片文件夹</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="group_id" label="所属分组">
            <Select
              allowClear
              placeholder="可不选择，导入后归入未分组"
              options={materialGroups.map((group) => ({ value: group.id, label: group.name }))}
              optionRender={renderGroupOption}
              labelRender={renderGroupOption}
            />
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
              <Descriptions.Item label="所属分组">{renderGroupTag(viewing.group_id)}</Descriptions.Item>
              <Descriptions.Item label="备注">{viewing.remark || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewing.created_at ? dayjs(viewing.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
            </Descriptions>
            {viewing.material_type === 'image' && viewing.file_path ? <Image src={viewing.file_path} width={240} /> : null}
            {viewing.material_type === 'text' ? <Input.TextArea value={viewing.content || ''} rows={6} readOnly /> : null}
            {viewing.material_type === 'contact' ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="手机号">{parseContact(viewing.content).phone_number || '-'}</Descriptions.Item>
                <Descriptions.Item label="Telegram 用户名">{parseContact(viewing.content).username || '-'}</Descriptions.Item>
                <Descriptions.Item label="名">{parseContact(viewing.content).first_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="姓">{parseContact(viewing.content).last_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="vCard">{parseContact(viewing.content).vcard || '-'}</Descriptions.Item>
              </Descriptions>
            ) : null}
          </Space>
        ) : null}
      </Drawer>

      <Modal
        title="导入TXT创建文字素材"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={() => importForm.submit()}
        confirmLoading={importMutation.isPending}
        destroyOnClose
      >
        <Form form={importForm} layout="vertical" onFinish={(values) => importMutation.mutate(values)}>
          <Form.Item
            name="file"
            label="选择TXT文件"
            valuePropName="fileList"
            getValueFromEvent={normFile}
            extra="不填写分隔符时，TXT 中每个非空行会创建为一条文字素材。"
            rules={[{ required: true, message: '请选择TXT文件' }]}
          >
            <Upload accept=".txt,text/plain" maxCount={1} beforeUpload={() => false}>
              <Button icon={<ImportOutlined />}>选择TXT文件</Button>
            </Upload>
          </Form.Item>
          <Form.Item
            name="delimiter"
            label="自定义分隔符"
            extra="可选。填写后将按该符号拆分素材，并保留每份素材内部的多行内容。例如填写 -----。"
            rules={[{ max: 100, message: '分隔符最多输入100个字符' }]}
          >
            <Input allowClear maxLength={100} placeholder="例如：-----（不填写则按一行一条拆分）" />
          </Form.Item>
          <Form.Item name="group_id" label="所属分组">
            <Select
              allowClear
              placeholder="可不选择，导入后归入未分组"
              options={materialGroups.map((group) => ({ value: group.id, label: group.name }))}
              optionRender={renderGroupOption}
              labelRender={renderGroupOption}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="素材分组管理" open={groupsOpen} onCancel={() => setGroupsOpen(false)} footer={null} width={720}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          style={{ marginBottom: 16 }}
          onClick={() => { setEditingGroup(null); groupForm.resetFields(); setGroupEditorOpen(true); }}
        >
          新建分组
        </Button>
        <Table
          rowKey="id"
          pagination={false}
          dataSource={materialGroups}
          columns={[
            { title: '分组名称', dataIndex: 'name', render: (value, group) => <Tag color={group.color || 'blue'}>{value}</Tag> },
            { title: '素材数', dataIndex: 'material_count', width: 100 },
            { title: '备注', dataIndex: 'remark', render: (value) => value || '-' },
            {
              title: '操作',
              width: 150,
              render: (_, group) => (
                <Space>
                  <Button size="small" onClick={() => { setEditingGroup(group); groupForm.setFieldsValue(group); setGroupEditorOpen(true); }}>编辑</Button>
                  <Popconfirm title="删除后组内素材将变为未分组，确认删除？" onConfirm={() => deleteGroupMutation.mutate(group.id)}>
                    <Button size="small" danger>删除</Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title={editingGroup ? '编辑素材分组' : '新建素材分组'}
        open={groupEditorOpen}
        onCancel={() => { setGroupEditorOpen(false); setEditingGroup(null); }}
        onOk={() => groupForm.submit()}
        confirmLoading={saveGroupMutation.isPending}
      >
        <Form form={groupForm} layout="vertical" onFinish={(values) => saveGroupMutation.mutate(values)}>
          <Form.Item name="name" label="分组名称" rules={[{ required: true, message: '请输入分组名称' }]}>
            <Input maxLength={150} />
          </Form.Item>
          <Form.Item name="color" label="Tag颜色" initialValue="blue">
            <Radio.Group>
              <Space wrap>
                {groupColorOptions.map((item) => (
                  <Radio key={item.value} value={item.value}>
                    <Tag color={item.value}>{item.label}</Tag>
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`批量转移 ${selectedRowKeys.length} 条素材`}
        open={moveOpen}
        onCancel={() => setMoveOpen(false)}
        onOk={() => moveMutation.mutate()}
        confirmLoading={moveMutation.isPending}
      >
        <Select
          value={moveGroupId}
          onChange={setMoveGroupId}
          allowClear
          placeholder="清空选择则转移至未分组"
          style={{ width: '100%' }}
          options={materialGroups.map((group) => ({ value: group.id, label: group.name }))}
          optionRender={renderGroupOption}
          labelRender={renderGroupOption}
        />
      </Modal>
    </div>
  );
}
