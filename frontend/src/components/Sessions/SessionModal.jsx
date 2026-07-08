import { Form, Input, Modal, Select } from 'antd';
import { useEffect } from 'react';

export default function SessionModal({ open, groups, initialValues, onCancel, onSubmit, confirmLoading }) {
  const [form] = Form.useForm();

  useEffect(() => {
    form.resetFields();
    if (initialValues) form.setFieldsValue(initialValues);
  }, [form, initialValues, open]);

  return (
    <Modal
      title={initialValues ? '编辑Session' : '添加Session'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={confirmLoading}
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={onSubmit}>
        <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item name="phone" label="手机号" rules={[{ required: true, message: '请输入手机号' }]}>
          <Input maxLength={32} />
        </Form.Item>
        <Form.Item name="avatar" label="头像URL">
          <Input maxLength={500} />
        </Form.Item>
        <Form.Item name="session_name" label="Session文件名">
          <Input maxLength={150} disabled={Boolean(initialValues)} />
        </Form.Item>
        <Form.Item name="group_id" label="分组">
          <Select
            allowClear
            options={groups.map((group) => ({ value: group.id, label: group.name }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
