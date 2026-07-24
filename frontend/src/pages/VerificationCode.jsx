import { CheckCircleOutlined, CopyOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Result, Space, Spin, Tag, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getSessionVerificationCode } from '../api/index.js';

export default function VerificationCode() {
  const { sessionId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await getSessionVerificationCode(sessionId));
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError.message || '获取验证码失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { refresh(); }, [refresh]);

  const copyCode = async () => {
    if (!data?.code) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(data.code);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = data.code;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        textarea.setSelectionRange(0, textarea.value.length);
        const copied = document.execCommand('copy');
        document.body.removeChild(textarea);
        if (!copied) throw new Error('浏览器拒绝访问剪贴板');
      }
      message.success('验证码已复制');
    } catch (copyError) {
      message.error(copyError?.message || '复制失败，请长按验证码手动复制');
    }
  };

  return (
    <div className="verification-code-page">
      <Card className="verification-code-card" bordered={false}>
        <Spin spinning={loading} tip="正在从 Telegram 获取最新验证码…">
          <Space direction="vertical" size={22} style={{ width: '100%' }}>
            <div className="verification-code-heading">
              <SafetyCertificateOutlined />
              <div>
                <Typography.Title level={3} style={{ margin: 0 }}>Telegram 登录验证码</Typography.Title>
                <Typography.Text type="secondary">{data?.username || data?.phone || data?.session_name || `Session #${sessionId}`}</Typography.Text>
              </div>
            </div>

            {error ? <Alert type="error" showIcon message="获取失败" description={error} /> : null}

            {!error && data?.code ? (
              <div className="verification-code-content">
                <Tag color={data.status === 'current' ? 'success' : 'gold'} icon={data.status === 'current' ? <CheckCircleOutlined /> : null}>
                  {data.status === 'current' ? '当前验证码' : '未来码（等待最新验证码）'}
                </Tag>
                <Typography.Text className="verification-code-value" copyable={false}>{data.code}</Typography.Text>
                <Typography.Text type="secondary">
                  接收时间：{data.received_at ? dayjs(data.received_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
                </Typography.Text>
              </div>
            ) : null}

            {!loading && !error && !data?.code ? (
              <Result status="info" title="未来码" subTitle="暂未找到验证码，请先在 Telegram App 发起登录，然后点击刷新验证码。" />
            ) : null}

            <Space className="verification-code-actions">
              <Button type="primary" size="large" icon={<CopyOutlined />} disabled={!data?.code} onClick={copyCode}>复制验证码</Button>
              <Button size="large" icon={<ReloadOutlined />} loading={loading} onClick={refresh}>刷新验证码</Button>
            </Space>
            <Alert type="warning" showIcon message="验证码属于敏感信息，请勿发送给不可信的人。" />
          </Space>
        </Spin>
      </Card>
    </div>
  );
}
