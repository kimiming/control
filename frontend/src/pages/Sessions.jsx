import { CheckCircleOutlined, ImportOutlined, PlusOutlined, TeamOutlined } from '@ant-design/icons';
import { Button, Drawer, Form, Input, Modal, Select, Space, Upload, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import {
  WS_BASE_URL,
  createGroup,
  createSession,
  deleteSession,
  getGroups,
  getSessionLogs,
  getSessions,
  importSessions,
  moveSessions,
  runHealthCheck,
  updateSession,
} from '../api/index.js';
import SessionList from '../components/Sessions/SessionList.jsx';
import SessionModal from '../components/Sessions/SessionModal.jsx';

export default function Sessions() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [moveGroupId, setMoveGroupId] = useState(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [groupForm] = Form.useForm();

  const { data: sessions = [], isLoading } = useQuery({ queryKey: ['sessions'], queryFn: () => getSessions() });
  const { data: groups = [] } = useQuery({ queryKey: ['session-groups'], queryFn: getGroups });
  const { data: logs = [] } = useQuery({
    queryKey: ['session-logs', logsOpen],
    queryFn: () => getSessionLogs({ limit: 100 }),
    enabled: logsOpen,
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

  const healthMutation = useMutation({
    mutationFn: runHealthCheck,
    onSuccess: (data) => message.success(`已检查 ${data.checked} 个Session`),
  });

  const uploadProps = useMemo(() => ({
    accept: '.csv,.xlsx,.xls',
    showUploadList: false,
    beforeUpload: async (file) => {
      const result = await importSessions(file);
      message.success(`导入成功 ${result.created} 条，跳过 ${result.skipped} 条`);
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      return false;
    },
  }), [queryClient]);

  return (
    <div className="page">
      <div className="toolbar">
        <div className="toolbar-left">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>添加</Button>
          <Upload {...uploadProps}>
            <Button icon={<ImportOutlined />}>批量导入</Button>
          </Upload>
          <Button icon={<TeamOutlined />} onClick={() => setGroupModalOpen(true)}>新建分组</Button>
          <Select
            allowClear
            placeholder="移动到分组"
            style={{ width: 180 }}
            value={moveGroupId}
            onChange={setMoveGroupId}
            options={groups.map((group) => ({ value: group.id, label: group.name }))}
          />
          <Button disabled={!selectedRowKeys.length} onClick={() => moveMutation.mutate()}>移动</Button>
        </div>
        <div className="toolbar-right">
          <Button icon={<CheckCircleOutlined />} loading={healthMutation.isPending} onClick={() => healthMutation.mutate()}>
            健康检查
          </Button>
          <Button onClick={() => setLogsOpen(true)}>操作日志</Button>
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
    </div>
  );
}
