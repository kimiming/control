import { DeleteOutlined, EditOutlined, EyeOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
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
  Progress,
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
import { useEffect, useMemo, useRef, useState } from 'react';

import { createTask, deleteTask, executeTask, getCustomerProfiles, getGroups, getMaterials, getTasks, updateTask } from '../api/index.js';

const statusColor = {
  draft: 'default',
  running: 'blue',
  completed: 'green',
  completed_with_errors: 'orange',
  failed: 'red',
};

const statusText = {
  draft: '草稿',
  running: '执行中',
  completed: '完成',
  completed_with_errors: '完成有失败',
  failed: '失败',
};

const buildTaskFormData = (values) => {
  const formData = new FormData();
  formData.append('name', values.name);
  if (values.content_mode !== 'material') {
    formData.append('content', values.content || '');
  }
  if (values.session_group_id !== undefined && values.session_group_id !== null) {
    formData.append('session_group_id', values.session_group_id);
  }
  formData.append('messages_per_target', values.messages_per_target ?? 3);
  if (values.content_mode === 'material' && values.content_material_id) {
    formData.append('content_material_id', values.content_material_id);
  }
  if (values.image_mode === 'material' && values.image_material_id) {
    formData.append('image_material_id', values.image_material_id);
  }
  if (values.contact_material_id) {
    formData.append('contact_material_id', values.contact_material_id);
  }
  if (values.targets_mode === 'profile' && values.customer_profile_id) {
    formData.append('customer_profile_id', values.customer_profile_id);
  }

  const imageFile = values.image?.[0]?.originFileObj;
  const targetsFile = values.targets_mode === 'profile' ? null : values.targets_file?.[0]?.originFileObj;
  if (imageFile) formData.append('image', imageFile);
  if (targetsFile) formData.append('targets_file', targetsFile);
  return formData;
};

const normFile = (event) => (Array.isArray(event) ? event : event?.fileList);

export default function Tasks() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [executingTaskIds, setExecutingTaskIds] = useState(() => new Set());
  const executingLocksRef = useRef(new Set());
  const [form] = Form.useForm();

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: getTasks,
    refetchInterval: (query) => {
      const rows = query.state.data || [];
      return rows.some((item) => item.status === 'running') || executingTaskIds.size ? 2000 : false;
    },
  });
  const { data: groups = [] } = useQuery({ queryKey: ['session-groups'], queryFn: getGroups });
  const { data: textMaterials = [] } = useQuery({ queryKey: ['materials', 'text'], queryFn: () => getMaterials({ material_type: 'text' }) });
  const { data: imageMaterials = [] } = useQuery({ queryKey: ['materials', 'image'], queryFn: () => getMaterials({ material_type: 'image' }) });
  const { data: contactMaterials = [] } = useQuery({ queryKey: ['materials', 'contact'], queryFn: () => getMaterials({ material_type: 'contact' }) });
  const { data: customerProfiles = [] } = useQuery({ queryKey: ['customer-profiles'], queryFn: getCustomerProfiles });
  const contentMode = Form.useWatch('content_mode', form);
  const imageMode = Form.useWatch('image_mode', form);
  const targetsMode = Form.useWatch('targets_mode', form);

  useEffect(() => {
    form.resetFields();
    if (editing) {
      form.setFieldsValue({
        name: editing.name,
        content: editing.content,
        content_mode: 'manual',
        image_mode: 'manual',
        targets_mode: 'manual',
        session_group_id: editing.session_group_id,
        messages_per_target: editing.messages_per_target,
        contact_material_id: editing.contact_card ? '__existing__' : undefined,
      });
    } else {
      form.setFieldsValue({ messages_per_target: 3, content_mode: 'manual', image_mode: 'manual', targets_mode: 'manual' });
    }
  }, [editing, form, modalOpen]);

  const groupNameMap = useMemo(() => {
    const map = new Map();
    groups.forEach((group) => map.set(group.id, group.name));
    return map;
  }, [groups]);

  const runningTaskIds = useMemo(
    () => new Set(tasks.filter((item) => item.status === 'running').map((item) => item.id)),
    [tasks],
  );

  const markTaskExecuting = (taskId, executing) => {
    if (executing) {
      executingLocksRef.current.add(taskId);
    } else {
      executingLocksRef.current.delete(taskId);
    }
    setExecutingTaskIds((prev) => {
      const next = new Set(prev);
      if (executing) {
        next.add(taskId);
      } else {
        next.delete(taskId);
      }
      return next;
    });
  };

  const isTaskLocked = (taskId) => executingTaskIds.has(taskId) || executingLocksRef.current.has(taskId) || runningTaskIds.has(taskId);

  const taskProgress = (record) => {
    if (record.status === 'completed' || record.status === 'completed_with_errors' || record.status === 'failed') {
      return 100;
    }
    const total = Math.max(record.total_targets || 0, 1);
    const done = Math.min((record.sent_count || 0) + (record.failed_count || 0), total);
    return Math.round((done / total) * 100);
  };

  const runTask = (taskId) => {
    if (isTaskLocked(taskId)) return;
    markTaskExecuting(taskId, true);
    executeMutation.mutate(taskId);
  };

  const saveMutation = useMutation({
    mutationFn: (values) => {
      const formData = buildTaskFormData(values);
      if (editing) return updateTask(editing.id, formData);
      return createTask(formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      setModalOpen(false);
      setEditing(null);
      message.success('任务已保存');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      message.success('任务已删除');
    },
  });

  const executeMutation = useMutation({
    mutationFn: executeTask,
    onMutate: (taskId) => {
      markTaskExecuting(taskId, true);
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      message.success(`任务执行完成，成功 ${task.sent_count} 条，失败 ${task.failed_count} 条`);
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
    onSettled: (_, __, taskId) => {
      markTaskExecuting(taskId, false);
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const columns = [
    { title: '任务名称', dataIndex: 'name', width: 180 },
    {
      title: '文字内容',
      dataIndex: 'content',
      ellipsis: true,
    },
    {
      title: 'Session分类',
      dataIndex: 'session_group_id',
      width: 140,
      render: (value) => (value ? groupNameMap.get(value) || value : '全部已连接'),
    },
    { title: '目标数', dataIndex: 'total_targets', width: 90 },
    { title: '每Session条数', dataIndex: 'messages_per_target', width: 120 },
    {
      title: '执行状态',
      dataIndex: 'status',
      width: 120,
      render: (value) => <Tag color={statusColor[value]}>{statusText[value] || value}</Tag>,
    },
    {
      title: '任务进度',
      key: 'progress',
      width: 180,
      render: (_, record) => (
        <Progress
          percent={taskProgress(record)}
          size="small"
          status={record.status === 'failed' ? 'exception' : record.status === 'running' ? 'active' : 'normal'}
        />
      ),
    },
    {
      title: '结果',
      key: 'result',
      width: 130,
      render: (_, record) => `${record.sent_count}/${record.failed_count}`,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 190,
      fixed: 'right',
      render: (_, record) => {
        const locked = isTaskLocked(record.id);
        return (
          <Space>
            <Tooltip title="执行">
              <Button
                className="task-run-button"
                icon={<PlayCircleOutlined />}
                loading={locked}
                disabled={locked}
                onClick={() => runTask(record.id)}
              />
            </Tooltip>
            <Tooltip title="查看">
              <Button icon={<EyeOutlined />} onClick={() => setViewing(record)} />
            </Tooltip>
            <Tooltip title="编辑">
              <Button icon={<EditOutlined />} onClick={() => { setEditing(record); setModalOpen(true); }} />
            </Tooltip>
            <Popconfirm title="确认删除该任务？" onConfirm={() => deleteMutation.mutate(record.id)}>
              <Tooltip title="删除">
                <Button danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div className="page">
      <div className="toolbar">
        <div className="toolbar-left">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setModalOpen(true); }}>
            新增任务
          </Button>
        </div>
      </div>

      <Table rowKey="id" columns={columns} dataSource={tasks} loading={isLoading} scroll={{ x: 1450 }} />

      <Modal
        title={editing ? '编辑任务' : '新增任务'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
        width={720}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => {
            const hasText = values.content_mode === 'material' ? Boolean(values.content_material_id) : Boolean(values.content?.trim());
            const hasImage = values.image_mode === 'material' ? Boolean(values.image_material_id) : Boolean(values.image?.[0]?.originFileObj || editing?.image_path);
            const hasContact = Boolean(values.contact_material_id) || Boolean(editing?.contact_card);
            if (!hasText && !hasImage && !hasContact) {
              message.error('任务文字、任务图片和名片至少填写一个');
              return;
            }
            if (values.contact_material_id === '__existing__') {
              values.contact_material_id = undefined;
            }
            if (values.targets_mode === 'profile' && !values.customer_profile_id) {
              message.error('请选择客户资料');
              return;
            }
            saveMutation.mutate(values);
          }}
        >
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input maxLength={150} />
          </Form.Item>
          <Form.Item name="content_mode" label="任务文字内容来源">
            <Radio.Group>
              <Radio value="manual">手动输入</Radio>
              <Radio value="material">选择素材</Radio>
            </Radio.Group>
          </Form.Item>
          {contentMode === 'material' ? (
            <Form.Item name="content_material_id" label="选择文字素材" rules={[{ required: true, message: '请选择文字素材' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={textMaterials.map((item) => ({ value: item.id, label: `${item.name}（优先级 ${item.priority}）` }))}
              />
            </Form.Item>
          ) : (
            <Form.Item name="content" label="任务文字内容">
              <Input.TextArea rows={5} maxLength={5000} showCount />
            </Form.Item>
          )}
          <Form.Item name="image_mode" label="任务图片来源">
            <Radio.Group>
              <Radio value="manual">手动上传</Radio>
              <Radio value="material">选择素材</Radio>
            </Radio.Group>
          </Form.Item>
          {imageMode === 'material' ? (
            <Form.Item name="image_material_id" label="选择图片素材" rules={[{ required: true, message: '请选择图片素材' }]}>
              <Select
                showSearch
                allowClear
                optionFilterProp="label"
                options={imageMaterials.map((item) => ({ value: item.id, label: `${item.name}（优先级 ${item.priority}）` }))}
              />
            </Form.Item>
          ) : (
            <Form.Item name="image" label="任务图片" valuePropName="fileList" getValueFromEvent={normFile}>
              <Upload accept="image/*" maxCount={1} beforeUpload={() => false} listType="picture">
                <Button>选择图片</Button>
              </Upload>
            </Form.Item>
          )}
          <Form.Item name="contact_material_id" label="选择名片素材">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="不发送名片可不选"
              options={[
                ...(editing?.contact_card ? [{ value: '__existing__', label: '保留原名片' }] : []),
                ...contactMaterials.map((item) => ({ value: item.id, label: `${item.name}（优先级 ${item.priority}）` })),
              ]}
            />
          </Form.Item>
          <Form.Item name="session_group_id" label="选择执行任务的Session分类">
            <Select
              allowClear
              placeholder="不选则使用全部已连接Session"
              options={groups.map((group) => ({ value: group.id, label: group.name }))}
            />
          </Form.Item>
          <Form.Item name="targets_mode" label="选择发送给谁">
            <Radio.Group>
              <Radio value="manual">手动导入</Radio>
              <Radio value="profile">选择客户资料</Radio>
            </Radio.Group>
          </Form.Item>
          {targetsMode === 'profile' ? (
            <Form.Item name="customer_profile_id" label="客户资料" rules={[{ required: true, message: '请选择客户资料' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={customerProfiles.map((item) => ({ value: item.id, label: `${item.name}（${item.total_count}个号码）` }))}
              />
            </Form.Item>
          ) : (
            <Form.Item
              name="targets_file"
              label="导入TXT"
              valuePropName="fileList"
              getValueFromEvent={normFile}
              rules={[{ required: !editing, message: '请导入手机号txt文件' }]}
            >
              <Upload accept=".txt" maxCount={1} beforeUpload={() => false}>
                <Button>导入TXT</Button>
              </Upload>
            </Form.Item>
          )}
          <Form.Item name="messages_per_target" label="每个Session成功发送条数" rules={[{ required: true, message: '请输入发送条数' }]}>
            <InputNumber min={1} max={50} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer title="任务详情" open={Boolean(viewing)} onClose={() => setViewing(null)} width={720}>
        {viewing ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="任务名称">{viewing.name}</Descriptions.Item>
              <Descriptions.Item label="Session分类">{viewing.session_group_id ? groupNameMap.get(viewing.session_group_id) || viewing.session_group_id : '全部已连接'}</Descriptions.Item>
              <Descriptions.Item label="每Session条数">{viewing.messages_per_target}</Descriptions.Item>
              <Descriptions.Item label="目标数">{viewing.total_targets}</Descriptions.Item>
              <Descriptions.Item label="状态">{statusText[viewing.status] || viewing.status}</Descriptions.Item>
              <Descriptions.Item label="成功/失败">{viewing.sent_count} / {viewing.failed_count}</Descriptions.Item>
              <Descriptions.Item label="最后执行">{viewing.last_run_at ? dayjs(viewing.last_run_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
              <Descriptions.Item label="错误">{viewing.error_message || '-'}</Descriptions.Item>
            </Descriptions>
            {viewing.image_path ? <Image src={viewing.image_path} width={220} /> : null}
            {viewing.contact_card ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="名片手机号">{viewing.contact_card.phone_number || '-'}</Descriptions.Item>
                <Descriptions.Item label="名">{viewing.contact_card.first_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="姓">{viewing.contact_card.last_name || '-'}</Descriptions.Item>
              </Descriptions>
            ) : null}
            <Input.TextArea value={viewing.content} rows={5} readOnly />
            <Input.TextArea value={(viewing.targets || []).join('\n')} rows={8} readOnly />
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
}
