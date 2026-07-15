import { DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, FileTextOutlined, PauseCircleOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons';
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
  Typography,
  Upload,
  message,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useMemo, useRef, useState } from 'react';

import { cancelTask, createTask, deleteTask, executeTask, exportTaskRemainingTargets, getCustomerProfiles, getGroups, getMaterialGroups, getMaterials, getSupportAgents, getTaskActiveSessions, getTaskLogs, getTaskSessionJobs, getTasks, pauseTask, requeueTaskSession, resumeTask, retryTaskUnsent, updateTask } from '../api/index.js';

const statusColor = {
  draft: 'default',
  queued: 'cyan',
  running: 'blue',
  paused: 'gold',
  cancelling: 'orange',
  cancelled: 'default',
  completed: 'green',
  completed_with_errors: 'orange',
  failed: 'red',
};

const statusText = {
  draft: '草稿',
  queued: '排队中',
  running: '执行中',
  paused: '已暂停',
  cancelling: '取消中',
  cancelled: '已取消',
  completed: '完成',
  completed_with_errors: '完成有失败',
  failed: '失败',
};

const buildTaskFormData = (values) => {
  const formData = new FormData();
  formData.append('name', values.name);
  formData.append('send_type', values.send_type || 'single');
  formData.append('target_type', values.target_type || 'phone');
  formData.append('target_source', values.target_source || 'imported');
  if (values.send_type === 'group') {
    if (values.material_group_id) formData.append('material_group_id', values.material_group_id);
  } else if (values.send_type === 'concat') {
    formData.append('material_group_ids', JSON.stringify(values.material_group_ids || []));
  } else if (values.content_mode !== 'material') {
    formData.append('content', values.content || '');
  }
  if (values.session_group_id !== undefined && values.session_group_id !== null) {
    formData.append('session_group_id', values.session_group_id);
  }
  formData.append('messages_per_target', values.messages_per_target ?? 3);
  formData.append('send_interval_min', values.send_interval_min ?? 3);
  formData.append('send_interval_max', values.send_interval_max ?? 5);
  if (values.send_type === 'single' && values.content_mode === 'material' && values.content_material_id) {
    formData.append('content_material_id', values.content_material_id);
  }
  if (values.send_type === 'single' && values.image_mode === 'material' && values.image_material_id) {
    formData.append('image_material_id', values.image_material_id);
  }
  if (values.send_type === 'single' && values.contact_material_id) {
    formData.append('contact_material_id', values.contact_material_id);
  }
  if (values.target_source !== 'contacts' && values.targets_mode === 'profile' && values.customer_profile_id) {
    formData.append('customer_profile_id', values.customer_profile_id);
  }

  const imageFile = values.send_type === 'single' ? values.image?.[0]?.originFileObj : null;
  const targetsFile = values.target_source === 'contacts' || values.targets_mode === 'profile' ? null : values.targets_file?.[0]?.originFileObj;
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
  const [logTask, setLogTask] = useState(null);
  const [logPage, setLogPage] = useState(1);
  const [logPageSize, setLogPageSize] = useState(20);
  const [logStatus, setLogStatus] = useState();
  const [logKeyword, setLogKeyword] = useState('');
  const [executingTaskIds, setExecutingTaskIds] = useState(() => new Set());
  const executingLocksRef = useRef(new Set());
  const [form] = Form.useForm();

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: getTasks,
    refetchInterval: (query) => {
      const rows = query.state.data || [];
      return rows.some((item) => ['queued', 'running', 'cancelling'].includes(item.status)) || executingTaskIds.size ? 2000 : false;
    },
  });
  const { data: groups = [] } = useQuery({ queryKey: ['session-groups'], queryFn: getGroups });
  const { data: supportAgents = [] } = useQuery({ queryKey: ['support-agents', 'tasks'], queryFn: getSupportAgents });
  const { data: materialGroups = [] } = useQuery({ queryKey: ['material-groups'], queryFn: getMaterialGroups });
  const { data: textMaterials = [] } = useQuery({ queryKey: ['materials', 'text'], queryFn: () => getMaterials({ material_type: 'text' }) });
  const { data: imageMaterials = [] } = useQuery({ queryKey: ['materials', 'image'], queryFn: () => getMaterials({ material_type: 'image' }) });
  const { data: contactMaterials = [] } = useQuery({ queryKey: ['materials', 'contact'], queryFn: () => getMaterials({ material_type: 'contact' }) });
  const { data: customerProfiles = [] } = useQuery({ queryKey: ['customer-profiles'], queryFn: getCustomerProfiles });
  const { data: taskLogsData = { items: [], total: 0 }, isLoading: taskLogsLoading } = useQuery({
    queryKey: ['task-logs', logTask?.id, logPage, logPageSize, logStatus, logKeyword],
    queryFn: () => getTaskLogs(logTask.id, { page: logPage, page_size: logPageSize, status: logStatus, keyword: logKeyword || undefined }),
    enabled: Boolean(logTask?.id),
    refetchInterval: ['queued', 'running', 'cancelling'].includes(logTask?.status) ? 3000 : false,
  });
  const { data: activeTaskSessions = [] } = useQuery({
    queryKey: ['task-active-sessions', viewing?.id],
    queryFn: () => getTaskActiveSessions(viewing.id),
    enabled: Boolean(viewing?.id),
    refetchInterval: viewing?.id ? 3000 : false,
  });
  const { data: taskSessionJobs = [] } = useQuery({
    queryKey: ['task-session-jobs', viewing?.id],
    queryFn: () => getTaskSessionJobs(viewing.id),
    enabled: Boolean(viewing?.id),
    refetchInterval: viewing?.id ? 5000 : false,
  });
  const contentMode = Form.useWatch('content_mode', form);
  const imageMode = Form.useWatch('image_mode', form);
  const targetsMode = Form.useWatch('targets_mode', form);
  const targetSource = Form.useWatch('target_source', form);
  const targetType = Form.useWatch('target_type', form);
  const sendType = Form.useWatch('send_type', form);

  useEffect(() => {
    form.resetFields();
    if (editing) {
      form.setFieldsValue({
        name: editing.name,
        content: editing.content,
        content_mode: 'manual',
        image_mode: 'manual',
        send_type: editing.send_type || 'single',
        material_group_id: editing.material_group_id,
        material_group_ids: editing.material_group_ids || [],
        targets_mode: 'manual',
        target_source: editing.target_source || 'imported',
        target_type: editing.target_type || 'phone',
        session_group_id: editing.session_group_id,
        messages_per_target: editing.messages_per_target,
        send_interval_min: editing.send_interval_min ?? 3,
        send_interval_max: editing.send_interval_max ?? 5,
        contact_material_id: editing.contact_card ? '__existing__' : undefined,
      });
    } else {
      form.setFieldsValue({ messages_per_target: 3, send_interval_min: 3, send_interval_max: 5, send_type: 'single', content_mode: 'manual', image_mode: 'manual', targets_mode: 'manual', target_source: 'imported', target_type: 'phone' });
    }
  }, [editing, form, modalOpen]);

  useEffect(() => {
    if (viewing) setViewing(tasks.find((item) => item.id === viewing.id) || viewing);
    if (logTask) setLogTask(tasks.find((item) => item.id === logTask.id) || logTask);
  }, [tasks]); // eslint-disable-line react-hooks/exhaustive-deps

  const groupNameMap = useMemo(() => {
    const map = new Map();
    groups.forEach((group) => map.set(group.id, group.name));
    return map;
  }, [groups]);
  const sessionGroupMap = useMemo(() => new Map(groups.map((group) => [group.id, group])), [groups]);
  const materialGroupNameMap = useMemo(() => new Map(materialGroups.map((group) => [group.id, group.name])), [materialGroups]);
  const groupAgentNameMap = useMemo(() => {
    const map = new Map();
    supportAgents.forEach((agent) => {
      const groupIds = Array.from(new Set((agent.sessions || []).map((session) => session.group_id).filter((groupId) => groupId != null)));
      groupIds.forEach((groupId) => {
        const agents = map.get(groupId) || [];
        if (!agents.some((item) => item.id === agent.id)) {
          agents.push({ id: agent.id, name: agent.name, color: agent.color || 'blue' });
        }
        map.set(groupId, agents);
      });
    });
    return map;
  }, [supportAgents]);
  const sessionGroupOptions = useMemo(
    () => groups.map((group) => {
      const agents = groupAgentNameMap.get(group.id) || [];
      const agentText = agents.length ? agents.map((item) => item.name).join('、') : '未绑定';
      return {
        value: group.id,
        label: `${group.name}（客服：${agentText}）`,
      };
    }),
    [groupAgentNameMap, groups],
  );

  const runningTaskIds = useMemo(
    () => new Set(tasks.filter((item) => ['queued', 'running', 'paused', 'cancelling'].includes(item.status)).map((item) => item.id)),
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
      queryClient.invalidateQueries({ queryKey: ['task-logs', task.id] });
      message.success('任务已进入后台发送队列');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
    onSettled: (_, __, taskId) => {
      markTaskExecuting(taskId, false);
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const controlMutation = useMutation({
    mutationFn: ({ id, action }) => {
      if (action === 'pause') return pauseTask(id);
      if (action === 'resume') return resumeTask(id);
      if (action === 'cancel') return cancelTask(id);
      return retryTaskUnsent(id);
    },
    onSuccess: (task, variables) => {
      const notices = { pause: '任务将在当前客户处理完成后暂停', resume: '任务已继续执行', cancel: '任务正在安全取消', retry: '明确未发送的客户已重新入队' };
      message.success(notices[variables.action]);
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['task-active-sessions', task.id] });
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const requeueSessionMutation = useMutation({
    mutationFn: ({ taskId, sessionId }) => requeueTaskSession(taskId, sessionId),
    onSuccess: (task) => {
      message.success('该Session明确未发送的客户已重新入队');
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['task-session-jobs', task.id] });
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const exportRemainingMutation = useMutation({
    mutationFn: (task) => exportTaskRemainingTargets(task.id),
    onSuccess: ({ blob, count }, task) => {
      if (!count) {
        message.info('该任务没有未发完的客户资料');
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeName = task.name.replace(/[\\/:*?"<>|]/g, '_');
      link.href = url;
      link.download = `${safeName}-未发完客户资料-${count}条.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success(`已导出 ${count} 个未处理客户`);
    },
    onError: async (error) => {
      let detail = error?.response?.data?.detail;
      if (error?.response?.data instanceof Blob) {
        try {
          detail = JSON.parse(await error.response.data.text()).detail;
        } catch {
          detail = null;
        }
      }
      message.error(detail || error.message || '导出失败');
    },
  });

  const columns = [
    { title: '任务名称', dataIndex: 'name', width: 180 },
    {
      title: '素材发送类型',
      dataIndex: 'send_type',
      width: 140,
      ellipsis: true,
      render: (value, record) => {
        if (value === 'group') return `组合：${materialGroupNameMap.get(record.material_group_id) || '分组已删除'}`;
        if (value === 'concat') {
          const names = (record.material_group_ids || []).map((id) => materialGroupNameMap.get(id) || '分组已删除');
          return `拼接：${names.join(' + ') || '-'}`;
        }
        return '单项发送';
      },
    },
    {
      title: 'Session分类',
      dataIndex: 'session_group_id',
      width: 140,
      render: (value) => {
        if (!value) return <Tag>全部已连接</Tag>;
        const group = sessionGroupMap.get(value);
        return <Tag color={group?.color || 'blue'}>{group?.name || '分组已删除'}</Tag>;
      },
    },
    {
      title: '客服',
      dataIndex: 'session_group_id',
      width: 180,
      render: (value) => {
        const agents = groupAgentNameMap.get(value) || [];
        if (!agents.length) return <Tag>未绑定</Tag>;
        return (
          <Space wrap size={[4, 4]}>
            {agents.map((agent) => (
              <Tag key={agent.id} color={agent.color || 'blue'}>{agent.name}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: '目标类型',
      key: 'target_source',
      width: 100,
      render: (_, record) => record.target_source === 'contacts'
        ? <Tag color="green">联系人好友</Tag>
        : <Tag color={record.target_type === 'username' ? 'purple' : 'blue'}>{record.target_type === 'username' ? '导入用户名' : '导入手机号'}</Tag>,
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
          status={record.status === 'failed' ? 'exception' : ['queued', 'running', 'cancelling'].includes(record.status) ? 'active' : 'normal'}
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
      width: 320,
      fixed: 'right',
      render: (_, record) => {
        const locked = isTaskLocked(record.id);
        const active = ['queued', 'running', 'paused', 'cancelling'].includes(record.status);
        return (
          <Space>
            {!active ? (
              <Tooltip title={record.status === 'draft' ? '执行' : '重试明确未发送客户'}>
                <Button
                  className="task-run-button"
                  icon={record.status === 'draft' ? <PlayCircleOutlined /> : <ReloadOutlined />}
                  loading={executingTaskIds.has(record.id)}
                  onClick={() => record.status === 'draft' ? runTask(record.id) : controlMutation.mutate({ id: record.id, action: 'retry' })}
                />
              </Tooltip>
            ) : null}
            {['queued', 'running'].includes(record.status) ? (
              <Tooltip title="安全暂停"><Button icon={<PauseCircleOutlined />} onClick={() => controlMutation.mutate({ id: record.id, action: 'pause' })} /></Tooltip>
            ) : null}
            {record.status === 'paused' ? (
              <Tooltip title="继续任务"><Button type="primary" icon={<PlayCircleOutlined />} onClick={() => controlMutation.mutate({ id: record.id, action: 'resume' })} /></Tooltip>
            ) : null}
            {['queued', 'running', 'paused'].includes(record.status) ? (
              <Tooltip title="安全取消"><Button danger icon={<StopOutlined />} onClick={() => controlMutation.mutate({ id: record.id, action: 'cancel' })} /></Tooltip>
            ) : null}
            <Tooltip title="查看">
              <Button icon={<EyeOutlined />} onClick={() => setViewing(record)} />
            </Tooltip>
            <Tooltip title="发送日志">
              <Button icon={<FileTextOutlined />} onClick={() => { setLogTask(record); setLogPage(1); setLogStatus(undefined); setLogKeyword(''); }} />
            </Tooltip>
            <Tooltip title="编辑">
              <Button disabled={locked} icon={<EditOutlined />} onClick={() => { setEditing(record); setModalOpen(true); }} />
            </Tooltip>
            <Popconfirm title="确认删除该任务？" onConfirm={() => deleteMutation.mutate(record.id)}>
              <Tooltip title="删除">
                <Button danger disabled={locked} icon={<DeleteOutlined />} />
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

      <Table rowKey="id" columns={columns} dataSource={tasks} loading={isLoading} scroll={{ x: 1280 }} />

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
          className="task-form"
          onFinish={(values) => {
            if (values.send_type === 'group' && !values.material_group_id) {
              message.error('请选择素材分组');
              return;
            }
            if (values.send_type === 'concat' && (values.material_group_ids || []).length < 2) {
              message.error('拼接发送至少选择两个文字素材分组');
              return;
            }
            if (values.send_type === 'single') {
              const hasText = values.content_mode === 'material' ? Boolean(values.content_material_id) : Boolean(values.content?.trim());
              const hasImage = values.image_mode === 'material' ? Boolean(values.image_material_id) : Boolean(values.image?.[0]?.originFileObj || editing?.image_path);
              const hasContact = Boolean(values.contact_material_id) || Boolean(editing?.contact_card);
              if (!hasText && !hasImage && !hasContact) {
                message.error('任务文字、任务图片和名片至少填写一个');
                return;
              }
              if (values.contact_material_id === '__existing__') values.contact_material_id = undefined;
            }
            if (values.target_source !== 'contacts' && values.targets_mode === 'profile' && !values.customer_profile_id) {
              message.error('请选择客户资料');
              return;
            }
            saveMutation.mutate(values);
          }}
        >
          <div className="task-form-section">
            <div className="task-form-section-title">1、任务名称</div>
            <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]} style={{ marginBottom: 0 }}>
              <Input maxLength={150} />
            </Form.Item>
          </div>

          <div className="task-form-section">
            <div className="task-form-section-title">2、素材发送类型</div>
            <Form.Item name="send_type" label="素材发送类型" rules={[{ required: true }]} style={{ marginBottom: 16 }}>
              <Radio.Group>
                <Radio value="single">单项发送</Radio>
                <Radio value="group">组合发送</Radio>
                <Radio value="concat">拼接发送</Radio>
              </Radio.Group>
            </Form.Item>
            {sendType === 'group' ? (
              <Form.Item
                name="material_group_id"
                label="选择素材分组"
                extra="支持文字、图片、名片或混合分组。每个客户只随机发送一条素材；优先级越高越可能先被抽取，一轮内所有素材发送成功后再重新随机。"
                rules={[{ required: true, message: '请选择素材分组' }]}
                style={{ marginBottom: 0 }}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={materialGroups.map((group) => ({
                    value: group.id,
                    label: `${group.name}（文字${group.text_count || 0} / 图片${group.image_count || 0} / 名片${group.contact_count || 0}）`,
                    disabled: !group.material_count,
                  }))}
                />
              </Form.Item>
            ) : sendType === 'concat' ? (
              <Form.Item
                name="material_group_ids"
                label="选择拼接素材分组"
                extra="按选择顺序，每个分组仅从文字素材中按优先级加权随机抽取一条，前一条结尾直接连接后一条开头，不自动添加换行或空格。"
                rules={[{ required: true, type: 'array', min: 2, message: '至少选择两个文字素材分组' }]}
                style={{ marginBottom: 0 }}
              >
                <Select
                  mode="multiple"
                  showSearch
                  optionFilterProp="label"
                  placeholder="请按拼接顺序选择至少两个分组"
                  options={materialGroups.map((group) => ({
                    value: group.id,
                    label: `${group.name}（${group.text_count || 0}条文字）`,
                    disabled: !group.text_count,
                  }))}
                />
              </Form.Item>
            ) : (
              <>
                <Form.Item name="content_mode" label="任务文字内容来源" style={{ marginBottom: 16 }}>
                  <Radio.Group>
                    <Radio value="manual">手动输入</Radio>
                    <Radio value="material">选择素材</Radio>
                  </Radio.Group>
                </Form.Item>
                {contentMode === 'material' ? (
                  <Form.Item name="content_material_id" label="选择文字素材" rules={[{ required: true, message: '请选择文字素材' }]} style={{ marginBottom: 16 }}>
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={textMaterials.map((item) => ({ value: item.id, label: `${item.name}（优先级 ${item.priority}）` }))}
                    />
                  </Form.Item>
                ) : (
                  <Form.Item name="content" label="任务文字内容" style={{ marginBottom: 16 }}>
                    <Input.TextArea rows={5} maxLength={5000} showCount />
                  </Form.Item>
                )}
                <Form.Item name="image_mode" label="任务图片来源" style={{ marginBottom: 16 }}>
                  <Radio.Group>
                    <Radio value="manual">手动上传</Radio>
                    <Radio value="material">选择素材</Radio>
                  </Radio.Group>
                </Form.Item>
                {imageMode === 'material' ? (
                  <Form.Item name="image_material_id" label="选择图片素材" rules={[{ required: true, message: '请选择图片素材' }]} style={{ marginBottom: 16 }}>
                    <Select
                      showSearch
                      allowClear
                      optionFilterProp="label"
                      options={imageMaterials.map((item) => ({ value: item.id, label: `${item.name}（优先级 ${item.priority}）` }))}
                    />
                  </Form.Item>
                ) : (
                  <Form.Item name="image" label="任务图片" valuePropName="fileList" getValueFromEvent={normFile} style={{ marginBottom: 16 }}>
                    <Upload accept="image/*" maxCount={1} beforeUpload={() => false} listType="picture">
                      <Button>选择图片</Button>
                    </Upload>
                  </Form.Item>
                )}
                <Form.Item name="contact_material_id" label="选择名片素材" style={{ marginBottom: 0 }}>
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
              </>
            )}
          </div>

          <div className="task-form-section">
            <div className="task-form-section-title">3、选择执行任务的Session分类</div>
            <Form.Item
              name="session_group_id"
              label="选择执行任务的Session分类"
              extra="请检查session分类是否绑定好客服，否则不能查看消息回复情况。"
              rules={[{ required: true, message: '请选择执行任务的Session分类' }]}
              style={{ marginBottom: 0 }}
            >
              <Select
                placeholder="请选择要执行任务的Session分类"
                options={sessionGroupOptions}
              />
            </Form.Item>
          </div>

          <div className="task-form-section">
            <div className="task-form-section-title">4、选择发送给谁</div>
            <Form.Item name="target_source" label="选择发送给谁" style={{ marginBottom: 16 }}>
              <Radio.Group>
                <Radio value="imported">导入数据</Radio>
                <Radio value="contacts">联系人好友</Radio>
              </Radio.Group>
            </Form.Item>
            {targetSource !== 'contacts' ? (
              <>
                <Form.Item name="targets_mode" label="导入数据方式" style={{ marginBottom: 16 }}>
                  <Radio.Group>
                    <Radio value="manual">手动导入TXT</Radio>
                    <Radio value="profile">选择客户资料</Radio>
                  </Radio.Group>
                </Form.Item>
                <Form.Item name="target_type" label="目标类型" rules={[{ required: true, message: '请选择目标类型' }]} style={{ marginBottom: 16 }}>
                  <Radio.Group
                    onChange={() => {
                      form.setFieldValue('customer_profile_id', undefined);
                      form.setFieldValue('targets_file', undefined);
                    }}
                  >
                    <Radio value="phone">手机号</Radio>
                    <Radio value="username">用户名</Radio>
                  </Radio.Group>
                </Form.Item>
                {targetsMode === 'profile' ? (
                  <Form.Item name="customer_profile_id" label="客户资料" rules={[{ required: true, message: '请选择客户资料' }]} style={{ marginBottom: 0 }}>
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={customerProfiles
                        .filter((item) => (item.target_type || 'phone') === (targetType || 'phone'))
                        .map((item) => ({ value: item.id, label: `${item.name}（${item.total_count}个）` }))}
                    />
                  </Form.Item>
                ) : (
                  <Form.Item
                    name="targets_file"
                    label="导入TXT"
                    valuePropName="fileList"
                    getValueFromEvent={normFile}
                    rules={[{ required: !editing, message: `请导入${targetType === 'username' ? '用户名' : '手机号'}TXT文件` }]}
                    style={{ marginBottom: 0 }}
                  >
                    <Upload accept=".txt" maxCount={1} beforeUpload={() => false}>
                      <Button>导入TXT</Button>
                    </Upload>
                  </Form.Item>
                )}
              </>
            ) : (
              <div className="task-form-tip">
                每个Session会从自己的Telegram通讯录好友中随机选择，最多成功发送下方设定的数量；无需导入TXT或选择客户资料。
              </div>
            )}
          </div>

          <div className="task-form-section">
            <div className="task-form-section-title">5、发送数量与间隔</div>
            <Form.Item name="messages_per_target" label="每个Session成功发送条数" rules={[{ required: true, message: '请输入发送条数' }]} style={{ marginBottom: 16 }}>
              <InputNumber min={1} max={50} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="每条发送间隔" extra="同一个Session每发送一个客户后，将在此范围内随机等待；默认3～5秒。" style={{ marginBottom: 0 }}>
              <Space.Compact block>
                <Form.Item
                  name="send_interval_min"
                  noStyle
                  dependencies={['send_interval_max']}
                  rules={[
                    { required: true, message: '请输入最小间隔' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        const maximum = getFieldValue('send_interval_max');
                        if (value == null || maximum == null || value <= maximum) return Promise.resolve();
                        return Promise.reject(new Error('最小间隔不能大于最大间隔'));
                      },
                    }),
                  ]}
                >
                  <InputNumber min={0} max={3600} precision={0} addonBefore="最小" addonAfter="秒" style={{ width: '50%' }} />
                </Form.Item>
                <Form.Item
                  name="send_interval_max"
                  noStyle
                  dependencies={['send_interval_min']}
                  rules={[
                    { required: true, message: '请输入最大间隔' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        const minimum = getFieldValue('send_interval_min');
                        if (value == null || minimum == null || value >= minimum) return Promise.resolve();
                        return Promise.reject(new Error('最大间隔不能小于最小间隔'));
                      },
                    }),
                  ]}
                >
                  <InputNumber min={0} max={3600} precision={0} addonBefore="最大" addonAfter="秒" style={{ width: '50%' }} />
                </Form.Item>
              </Space.Compact>
            </Form.Item>
          </div>
        </Form>
      </Modal>

      <Drawer title="任务详情" open={Boolean(viewing)} onClose={() => setViewing(null)} width={720}>
        {viewing ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {viewing.target_source !== 'contacts' && ['completed', 'completed_with_errors', 'failed', 'cancelled'].includes(viewing.status) ? (
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                loading={exportRemainingMutation.isPending}
                onClick={() => exportRemainingMutation.mutate(viewing)}
              >
                导出未发完的客户资料
              </Button>
            ) : null}
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="任务名称">{viewing.name}</Descriptions.Item>
              <Descriptions.Item label="素材发送类型">
                {viewing.send_type === 'group'
                  ? `组合发送：${materialGroupNameMap.get(viewing.material_group_id) || '分组已删除'}`
                  : viewing.send_type === 'concat'
                    ? `拼接发送：${(viewing.material_group_ids || []).map((id) => materialGroupNameMap.get(id) || '分组已删除').join(' + ')}`
                    : '单项发送'}
              </Descriptions.Item>
              <Descriptions.Item label="Session分类">{viewing.session_group_id ? groupNameMap.get(viewing.session_group_id) || viewing.session_group_id : '全部已连接'}</Descriptions.Item>
              <Descriptions.Item label="发送对象">{viewing.target_source === 'contacts' ? '联系人好友' : (viewing.target_type === 'username' ? '导入用户名' : '导入手机号')}</Descriptions.Item>
              <Descriptions.Item label="每Session条数">{viewing.messages_per_target}</Descriptions.Item>
              <Descriptions.Item label="发送间隔">随机 {viewing.send_interval_min ?? 3}～{viewing.send_interval_max ?? 5} 秒</Descriptions.Item>
              <Descriptions.Item label="目标数">{viewing.total_targets}</Descriptions.Item>
              <Descriptions.Item label="状态">{statusText[viewing.status] || viewing.status}</Descriptions.Item>
              <Descriptions.Item label="成功/失败">{viewing.sent_count} / {viewing.failed_count}</Descriptions.Item>
              <Descriptions.Item label="已分配/排队中">{viewing.stats?.assigned ?? 0} / {viewing.stats?.queued ?? 0}</Descriptions.Item>
              <Descriptions.Item label="发送中/未处理">{viewing.stats?.processing ?? 0} / {viewing.stats?.unprocessed ?? 0}</Descriptions.Item>
              <Descriptions.Item label="结果不确定">{viewing.stats?.uncertain ?? 0}</Descriptions.Item>
              <Descriptions.Item label="受限Session/异常代理">{viewing.stats?.throttled_sessions ?? 0} / {viewing.stats?.abnormal_proxies ?? 0}</Descriptions.Item>
              <Descriptions.Item label="当前并发">{viewing.stats?.current_concurrency ?? 0}</Descriptions.Item>
              <Descriptions.Item label="发送速度">{viewing.stats?.speed_per_minute ?? 0} 条/分钟</Descriptions.Item>
              <Descriptions.Item label="预计剩余时间">{viewing.stats?.eta_minutes == null ? '-' : `${viewing.stats.eta_minutes} 分钟`}</Descriptions.Item>
              <Descriptions.Item label="最后执行">{viewing.last_run_at ? dayjs(viewing.last_run_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
              <Descriptions.Item label="错误">{viewing.error_message || '-'}</Descriptions.Item>
            </Descriptions>
            <Typography.Title level={5}>当前正在工作的Session（{activeTaskSessions.length}）</Typography.Title>
            <Table
              size="small"
              rowKey="session_id"
              dataSource={activeTaskSessions}
              pagination={false}
              columns={[
                { title: 'Session', dataIndex: 'session_name' },
                { title: '手机号', dataIndex: 'session_phone' },
                { title: '当前客户', dataIndex: 'target' },
                { title: '开始时间', dataIndex: 'started_at', render: (value) => value ? dayjs(value).format('HH:mm:ss') : '-' },
              ]}
            />
            <Typography.Title level={5}>Session作业明细</Typography.Title>
            <Table
              size="small"
              rowKey="session_id"
              dataSource={taskSessionJobs}
              pagination={{ pageSize: 10, showSizeChanger: true }}
              columns={[
                { title: 'Session', dataIndex: 'session_name' },
                { title: '成功', render: (_, row) => row.counts?.success || 0 },
                { title: '失败', render: (_, row) => row.counts?.failed || 0 },
                { title: '排队/发送中', render: (_, row) => `${row.counts?.queued || 0}/${row.counts?.processing || 0}` },
                { title: '可重排', dataIndex: 'requeueable' },
                {
                  title: '操作',
                  render: (_, row) => (
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      disabled={!row.requeueable || ['queued', 'running', 'cancelling'].includes(viewing.status)}
                      onClick={() => requeueSessionMutation.mutate({ taskId: viewing.id, sessionId: row.session_id })}
                    >
                      重新入队
                    </Button>
                  ),
                },
              ]}
            />
            {viewing.send_type === 'single' && viewing.image_path ? <Image src={viewing.image_path} width={220} /> : null}
            {viewing.send_type === 'single' && viewing.contact_card ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="名片手机号">{viewing.contact_card.phone_number || '-'}</Descriptions.Item>
                <Descriptions.Item label="名">{viewing.contact_card.first_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="姓">{viewing.contact_card.last_name || '-'}</Descriptions.Item>
              </Descriptions>
            ) : null}
            {viewing.send_type === 'single' ? <Input.TextArea value={viewing.content} rows={5} readOnly /> : null}
            {viewing.target_source !== 'contacts' ? <Input.TextArea value={(viewing.targets || []).join('\n')} rows={8} readOnly /> : null}
          </Space>
        ) : null}
      </Drawer>

      <Drawer
        title={logTask ? `${logTask.name} - 发送日志` : '发送日志'}
        open={Boolean(logTask)}
        onClose={() => setLogTask(null)}
        width={980}
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            allowClear
            placeholder="发送结果"
            style={{ width: 140 }}
            value={logStatus}
            onChange={(value) => { setLogStatus(value); setLogPage(1); }}
            options={[{ value: 'success', label: '成功' }, { value: 'failed', label: '失败' }]}
          />
          <Input.Search
            allowClear
            placeholder="搜索客户或详情"
            style={{ width: 260 }}
            onSearch={(value) => { setLogKeyword(value.trim()); setLogPage(1); }}
          />
          <Typography.Text type="secondary">共 {taskLogsData.total || 0} 条日志</Typography.Text>
        </Space>
        <Table
          rowKey="id"
          loading={taskLogsLoading}
          dataSource={taskLogsData.items || []}
          pagination={{
            current: logPage,
            pageSize: logPageSize,
            total: taskLogsData.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, pageSize) => { setLogPage(pageSize !== logPageSize ? 1 : page); setLogPageSize(pageSize); },
          }}
          scroll={{ x: 900 }}
          columns={[
            {
              title: 'Session号',
              key: 'session',
              width: 220,
              render: (_, log) => (
                <Space direction="vertical" size={0}>
                  <Typography.Text strong>{log.session_name || '系统汇总'}</Typography.Text>
                  <Typography.Text type="secondary">{log.session_phone || '-'}</Typography.Text>
                </Space>
              ),
            },
            { title: '目标客户', dataIndex: 'target_customer', width: 160 },
            {
              title: '发送结果',
              dataIndex: 'status',
              width: 110,
              render: (value) => <Tag color={value === 'success' ? 'green' : 'red'}>{value === 'success' ? '成功' : '失败'}</Tag>,
            },
            { title: '发送详情', dataIndex: 'message', ellipsis: true, render: (value) => value || '-' },
            {
              title: '发送到达时间',
              dataIndex: 'sent_at',
              width: 180,
              render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
            },
          ]}
        />
      </Drawer>
    </div>
  );
}
