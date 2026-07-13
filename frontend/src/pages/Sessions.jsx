import { CheckCircleOutlined, DeleteOutlined, ImportOutlined, LinkOutlined, SafetyCertificateOutlined, TeamOutlined } from '@ant-design/icons';
import { Button, Card, Drawer, Form, Input, Modal, Popconfirm, Radio, Select, Space, Table, Tag, Upload, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useMemo, useState } from 'react';
import {
  WS_BASE_URL,
  createGroup,
  createSession,
  deleteSession,
  getGroups,
  getSessionLogs,
  getSessionTaskLogs,
  getSessions,
  getSupportAgents,
  getProxies,
  importSessions,
  moveSessions,
  moveSessionsToAgent,
  moveSessionsToProxy,
  runHealthCheck,
  checkSessionBidirectional,
  checkAllSessionsBidirectional,
  updateSession,
} from '../api/index.js';
import SessionList from '../components/Sessions/SessionList.jsx';
import SessionModal from '../components/Sessions/SessionModal.jsx';

const groupColorOptions = [
  { label: '红', value: 'red' },
  { label: '橙', value: 'orange' },
  { label: '黄', value: 'yellow' },
  { label: '绿', value: 'green' },
  { label: '蓝', value: 'blue' },
  { label: '靛', value: 'geekblue' },
  { label: '紫', value: 'purple' },
];

const sessionStatusOptions = [
  { label: '已连接', value: 'connected' },
  { label: '连接中', value: 'connecting' },
  { label: '未连接', value: 'disconnected' },
  { label: '异常', value: 'error' },
];

const healthStatusOptions = [
  { label: '健康', value: 'healthy' },
  { label: '异常', value: 'unhealthy' },
  { label: '未知', value: 'unknown' },
  { label: '未检查', value: 'unchecked' },
  { label: '未授权', value: 'unauthorized' },
  { label: '受限', value: 'restricted' },
  { label: '监听异常', value: 'listener_error' },
];

export default function Sessions() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [moveGroupId, setMoveGroupId] = useState(null);
  const [moveAgentId, setMoveAgentId] = useState(null);
  const [moveProxyId, setMoveProxyId] = useState(null);
  const [filters, setFilters] = useState({});
  const [logsOpen, setLogsOpen] = useState(false);
  const [taskLogSession, setTaskLogSession] = useState(null);
  const [groupForm] = Form.useForm();

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['sessions', filters],
    queryFn: () => getSessions(filters),
  });
  const { data: groups = [] } = useQuery({ queryKey: ['session-groups'], queryFn: getGroups });
  const { data: supportAgents = [] } = useQuery({ queryKey: ['support-agents'], queryFn: getSupportAgents });
  const { data: proxies = [] } = useQuery({ queryKey: ['proxies'], queryFn: getProxies });
  const { data: logs = [] } = useQuery({
    queryKey: ['session-logs', logsOpen],
    queryFn: () => getSessionLogs({ limit: 100 }),
    enabled: logsOpen,
  });
  const { data: taskLogs = [], isLoading: taskLogsLoading } = useQuery({
    queryKey: ['session-task-logs', taskLogSession?.id],
    queryFn: () => getSessionTaskLogs(taskLogSession.id, { limit: 200 }),
    enabled: Boolean(taskLogSession?.id),
  });

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE_URL}/sessions/all`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.event === 'deleted') {
        queryClient.setQueryData(['sessions'], (old = []) => old.filter((item) => item.id !== payload.id));
        return;
      }
      if (payload.session) {
        queryClient.setQueryData(['sessions'], (old = []) => {
          const exists = old.some((item) => item.id === payload.session.id);
          if (!exists) return [payload.session, ...old];
          return old.map((item) => (item.id === payload.session.id ? { ...item, ...payload.session } : item));
        });
      }
    };
    socket.onclose = () => setTimeout(() => queryClient.invalidateQueries({ queryKey: ['sessions'] }), 1000);
    return () => socket.close();
  }, [queryClient]);

  const saveMutation = useMutation({
    mutationFn: (values) => (editing ? updateSession(editing.id, values) : createSession(values)),
    onSuccess: (data) => {
      queryClient.setQueryData(['sessions'], (old = []) => {
        const exists = old.some((item) => item.id === data.id);
        return exists ? old.map((item) => (item.id === data.id ? data : item)) : [data, ...old];
      });
      setModalOpen(false);
      setEditing(null);
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }) => updateSession(id, { action }),
    onSuccess: (data) => {
      queryClient.setQueryData(['sessions'], (old = []) => old.map((item) => (item.id === data.id ? data : item)));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (record) => deleteSession(record.id),
    onSuccess: (_, record) => {
      queryClient.setQueryData(['sessions'], (old = []) => old.filter((item) => item.id !== record.id));
    },
  });

  const batchDeleteMutation = useMutation({
    mutationFn: async () => {
      const results = await Promise.allSettled(selectedRowKeys.map((id) => deleteSession(id)));
      const failed = results.filter((result) => result.status === 'rejected');
      if (failed.length) {
        throw new Error(`删除失败 ${failed.length} 个，成功 ${results.length - failed.length} 个`);
      }
      return results.length;
    },
    onSuccess: (count) => {
      message.success(`已删除 ${count} 个Session`);
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      setSelectedRowKeys([]);
    },
    onError: (error) => {
      message.error(error.message || '批量删除失败');
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });

  const batchConnectMutation = useMutation({
    mutationFn: async () => {
      const results = await Promise.allSettled(selectedRowKeys.map((id) => updateSession(id, { action: 'connect' })));
      const failed = results.filter((result) => result.status === 'rejected');
      if (failed.length) {
        throw new Error(`连接失败 ${failed.length} 个，成功 ${results.length - failed.length} 个`);
      }
      return results.length;
    },
    onSuccess: (count) => {
      message.success(`已提交 ${count} 个Session连接`);
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      setSelectedRowKeys([]);
    },
    onError: (error) => {
      message.error(error.message || '批量连接失败');
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });

  const groupMutation = useMutation({
    mutationFn: createGroup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session-groups'] });
      setGroupModalOpen(false);
      groupForm.resetFields();
    },
  });

  const moveMutation = useMutation({
    mutationFn: () => moveSessions({ session_ids: selectedRowKeys, group_id: moveGroupId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      setSelectedRowKeys([]);
    },
  });

  const moveAgentMutation = useMutation({
    mutationFn: () => moveSessionsToAgent({ session_ids: selectedRowKeys, kf_id: moveAgentId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      setSelectedRowKeys([]);
    },
  });

  const moveProxyMutation = useMutation({
    mutationFn: () => moveSessionsToProxy({ session_ids: selectedRowKeys, proxy_id: moveProxyId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      queryClient.invalidateQueries({ queryKey: ['proxies'] });
      setSelectedRowKeys([]);
    },
  });

  const healthMutation = useMutation({
    mutationFn: runHealthCheck,
    onSuccess: (data) => message.success(`已检查 ${data.checked} 个Session`),
  });

  const bidirectionalMutation = useMutation({
    mutationFn: (record) => checkSessionBidirectional(record.id),
    onSuccess: (data) => {
      queryClient.setQueriesData({ queryKey: ['sessions'] }, (old = []) => (
        Array.isArray(old) ? old.map((item) => (item.id === data.id ? { ...item, ...data } : item)) : old
      ));
      const resultText = {
        normal: '账号正常，不是双向号',
        restricted: '账号异常，疑似双向号',
        timeout: '检测超时',
        unauthorized: 'Session 未授权',
        error: '检测异常',
      }[data.bidirectional_status] || data.bidirectional_status;
      if (data.bidirectional_status === 'normal') message.success(resultText);
      else message.warning(resultText);
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message || '双向号检测失败'),
  });

  const batchBidirectionalMutation = useMutation({
    mutationFn: checkAllSessionsBidirectional,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      message.success(
        `批量检测完成：共 ${data.checked} 个，正常 ${data.normal} 个，疑似双向号 ${data.restricted} 个，超时 ${data.timeout} 个，未授权 ${data.unauthorized} 个，异常 ${data.error} 个`,
        8,
      );
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message || '批量双向号检测失败'),
  });

  const uploadProps = useMemo(() => ({
    accept: '.session,.csv,.xlsx,.xls,.txt',
    multiple: true,
    showUploadList: false,
    beforeUpload: async (file) => {
      try {
        const result = await importSessions(file);
        message.success(`${file.name} 导入成功 ${result.created} 条，跳过 ${result.skipped} 条`);
        queryClient.invalidateQueries({ queryKey: ['sessions'] });
      } catch (error) {
        message.error(`${file.name} 导入失败：${error?.response?.data?.detail || error.message}`);
      }
      return false;
    },
  }), [queryClient]);

  const renderSupportAgentOption = (option) => {
    if (option.value === 0) return <Tag>未绑定</Tag>;
    const agent = supportAgents.find((item) => item.id === option.value);
    return <Tag color={agent?.color || 'blue'}>{option.label}</Tag>;
  };

  const renderGroupOption = (option) => {
    if (option.value === 0) return <Tag>未分组</Tag>;
    const group = groups.find((item) => item.id === option.value);
    return <Tag color={group?.color || 'blue'}>{option.label}</Tag>;
  };

  const groupSelectOptions = [
    { value: 0, label: '未分组' },
    ...groups.map((group) => ({ value: group.id, label: group.name })),
  ];

  const renderProxyOption = (option) => {
    if (option.value === 0) return <Tag>未分配</Tag>;
    const proxy = proxies.find((item) => item.id === option.value);
    return <Tag color={proxy?.is_active ? 'green' : 'default'}>{option.label}</Tag>;
  };

  const proxySelectOptions = [
    { value: 0, label: '未分配' },
    ...proxies.map((proxy) => ({ value: proxy.id, label: proxy.name })),
  ];

  return (
    <div className="page">
      <Card size="small" className="filter-card" title="搜索筛选">
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="搜索手机号、用户名、Session名"
            style={{ width: 260 }}
            onSearch={(value) => setFilters((old) => ({ ...old, keyword: value || undefined }))}
          />
          <Select
            allowClear
            placeholder="按分组筛选"
            style={{ width: 180 }}
            value={filters.group_id}
            onChange={(value) => setFilters((old) => ({ ...old, group_id: value }))}
            options={groupSelectOptions}
            optionRender={renderGroupOption}
            labelRender={renderGroupOption}
          />
          <Select
            allowClear
            placeholder="按客服筛选"
            style={{ width: 180 }}
            value={filters.kf_id}
            onChange={(value) => setFilters((old) => ({ ...old, kf_id: value }))}
            options={[
              { value: 0, label: '未绑定' },
              ...supportAgents.map((agent) => ({ value: agent.id, label: agent.name })),
            ]}
            optionRender={renderSupportAgentOption}
          />
          <Select
            allowClear
            placeholder="连接状态"
            style={{ width: 150 }}
            value={filters.status}
            onChange={(value) => setFilters((old) => ({ ...old, status: value }))}
            options={sessionStatusOptions}
          />
          <Select
            allowClear
            placeholder="健康状态"
            style={{ width: 150 }}
            value={filters.health_status}
            onChange={(value) => setFilters((old) => ({ ...old, health_status: value }))}
            options={healthStatusOptions}
          />
          <Button onClick={() => setFilters({})}>重置</Button>
        </Space>
      </Card>
      <div className="session-action-panel">
        <div className="session-action-row">
          <Upload {...uploadProps}>
            <Button type="primary" icon={<ImportOutlined />}>批量导入</Button>
          </Upload>
          <Popconfirm
            title={`确认删除选中的 ${selectedRowKeys.length} 个Session？`}
            disabled={!selectedRowKeys.length}
            onConfirm={() => batchDeleteMutation.mutate()}
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={!selectedRowKeys.length}
              loading={batchDeleteMutation.isPending}
            >
              批量删除
            </Button>
          </Popconfirm>
          <Button
            icon={<LinkOutlined />}
            disabled={!selectedRowKeys.length}
            loading={batchConnectMutation.isPending}
            onClick={() => batchConnectMutation.mutate()}
          >
            批量连接
          </Button>
          <Button
            icon={<TeamOutlined />}
            onClick={() => {
              groupForm.setFieldsValue({ color: 'blue' });
              setGroupModalOpen(true);
            }}
          >
            新建分组
          </Button>
          <Button
            icon={<CheckCircleOutlined />}
            loading={healthMutation.isPending}
            disabled={batchBidirectionalMutation.isPending}
            onClick={() => healthMutation.mutate()}
          >
            健康检查
          </Button>
          <Button
            icon={<SafetyCertificateOutlined />}
            loading={batchBidirectionalMutation.isPending}
            disabled={bidirectionalMutation.isPending || healthMutation.isPending}
            onClick={() => batchBidirectionalMutation.mutate()}
          >
            批量双向号检测
          </Button>
          <Button onClick={() => setLogsOpen(true)}>操作日志</Button>
        </div>
        <div className="session-action-row session-move-row">
          <Select
            allowClear
            placeholder="移动到分组"
            style={{ width: 200 }}
            value={moveGroupId}
            onChange={setMoveGroupId}
            options={groupSelectOptions}
            optionRender={renderGroupOption}
            labelRender={renderGroupOption}
          />
          <Button disabled={!selectedRowKeys.length || moveGroupId == null} onClick={() => moveMutation.mutate()}>移动</Button>
          <Select
            allowClear
            placeholder="移动到客服"
            style={{ width: 200 }}
            value={moveAgentId}
            onChange={setMoveAgentId}
            options={[
              { value: 0, label: '未绑定' },
              ...supportAgents.map((agent) => ({ value: agent.id, label: agent.name })),
            ]}
            optionRender={renderSupportAgentOption}
          />
          <Button
            disabled={!selectedRowKeys.length || moveAgentId == null}
            loading={moveAgentMutation.isPending}
            onClick={() => moveAgentMutation.mutate()}
          >
            移动客服
          </Button>
          <Select
            allowClear
            placeholder="移动到代理"
            style={{ width: 200 }}
            value={moveProxyId}
            onChange={setMoveProxyId}
            options={proxySelectOptions}
            optionRender={renderProxyOption}
            labelRender={renderProxyOption}
          />
          <Button
            disabled={!selectedRowKeys.length || moveProxyId == null}
            loading={moveProxyMutation.isPending}
            onClick={() => moveProxyMutation.mutate()}
          >
            移动分组代理
          </Button>
        </div>
      </div>
      <SessionList
        sessions={sessions}
        loading={isLoading}
        selectedRowKeys={selectedRowKeys}
        onSelectionChange={setSelectedRowKeys}
        onEdit={(record) => { setEditing(record); setModalOpen(true); }}
        onConnect={(record) => actionMutation.mutate({ id: record.id, action: 'connect' })}
        onDisconnect={(record) => actionMutation.mutate({ id: record.id, action: 'disconnect' })}
        onDelete={(record) => deleteMutation.mutate(record)}
        onTaskLogs={(record) => setTaskLogSession(record)}
        onBidirectionalCheck={(record) => bidirectionalMutation.mutate(record)}
        checkingSessionId={batchBidirectionalMutation.isPending ? -1 : (bidirectionalMutation.isPending ? bidirectionalMutation.variables?.id : null)}
      />
      <SessionModal
        open={modalOpen}
        groups={groups}
        initialValues={editing}
        confirmLoading={saveMutation.isPending}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onSubmit={(values) => saveMutation.mutate(values)}
      />
      <Modal title="新建分组" open={groupModalOpen} onCancel={() => setGroupModalOpen(false)} onOk={() => groupForm.submit()}>
        <Form form={groupForm} layout="vertical" onFinish={(values) => groupMutation.mutate(values)}>
          <Form.Item name="name" label="分组名称" rules={[{ required: true, message: '请输入分组名称' }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input maxLength={255} />
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
        </Form>
      </Modal>
      <Drawer title="Session操作日志" open={logsOpen} onClose={() => setLogsOpen(false)} width={640}>
        <Space direction="vertical" style={{ width: '100%' }}>
          {logs.map((log) => (
            <div key={log.id}>
              <strong>{log.action}</strong> #{log.session_id || '-'} {log.message}
              <div style={{ color: '#667085' }}>{log.created_at}</div>
            </div>
          ))}
        </Space>
      </Drawer>
      <Drawer
        title={taskLogSession ? `${taskLogSession.username} 的任务日志` : '任务日志'}
        open={Boolean(taskLogSession)}
        onClose={() => setTaskLogSession(null)}
        width={860}
      >
        <Table
          rowKey="id"
          loading={taskLogsLoading}
          dataSource={taskLogs}
          pagination={{ pageSize: 20 }}
          columns={[
            { title: '任务', dataIndex: 'task_name', width: 180 },
            { title: '目标手机号', dataIndex: 'target_phone', width: 150 },
            {
              title: '结果',
              dataIndex: 'status',
              width: 100,
              render: (value) => <Tag color={value === 'success' ? 'green' : 'red'}>{value === 'success' ? '成功' : '失败'}</Tag>,
            },
            { title: '说明', dataIndex: 'message', ellipsis: true },
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 180,
              render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
            },
          ]}
        />
      </Drawer>
    </div>
  );
}
