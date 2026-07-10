import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';

export default function Login() {
  const navigate = useNavigate();
  const auth = useAuth();

  if (auth.token && auth.user) {
    return <Navigate to="/sessions" replace />;
  }

  const submit = async (values) => {
    try {
      await auth.login(values);
      navigate('/sessions', { replace: true });
    } catch (error) {
      message.error(error?.response?.data?.detail || error.message);
    }
  };

  return (
    <div className="login-page">
      <Card className="login-card">
        <Typography.Title level={3}>登录</Typography.Title>
        <Form layout="vertical" onFinish={submit}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
