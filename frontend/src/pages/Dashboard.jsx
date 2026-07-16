import {
  AppstoreOutlined,
  CheckCircleOutlined,
  ContactsOutlined,
  MessageOutlined,
  ProfileOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Button, Card, Progress, Skeleton, Table, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, GaugeChart, LineChart, PieChart } from 'echarts/charts';
import { GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { getDashboardStatistics } from '../api/index.js';

echarts.use([
  BarChart,
  GaugeChart,
  LineChart,
  PieChart,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const palette = ['#167c80', '#e07a3f', '#2f5d8a', '#d0a52b', '#c94f5d', '#638b63', '#728197'];
const numberFormatter = new Intl.NumberFormat('zh-CN');

const labels = {
  connected: '已连接', connecting: '连接中', disconnected: '未连接', error: '异常',
  healthy: '健康', unhealthy: '异常', unknown: '未知', unchecked: '未检查', unauthorized: '未授权', listener_error: '监听异常',
  normal: '正常', blocked: '已封禁', restricted: '疑似双向号', timeout: '超时', checking: '检测中',
  inbound: '客户消息', outbound: '发送消息', replied: '已回复', not_replied: '未回复',
  text: '文字', image: '图片', contact: '名片', phone: '手机号', username: '用户名',
  draft: '草稿', queued: '排队中', running: '执行中', paused: '已暂停', completed: '已完成', failed: '失败', cancelled: '已取消', cancelling: '取消中',
  completed_with_errors: '完成有失败',
};

function toPieData(source = {}) {
  return Object.entries(source).map(([name, value]) => ({ name: labels[name] || name, value }));
}

function pieOption(source, centerText) {
  return {
    color: palette,
    animationDuration: 900,
    animationEasing: 'cubicOut',
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c}（{d}%）' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 9, textStyle: { color: '#52606d' } },
    graphic: [{
      type: 'text', left: 'center', top: '39%',
      style: { text: centerText, fill: '#1f3447', fontSize: 13, fontWeight: 700, textAlign: 'center' },
    }],
    series: [{
      type: 'pie', radius: ['48%', '70%'], center: ['50%', '43%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 6 },
      label: { show: false }, emphasis: { scaleSize: 8 },
      data: toPieData(source),
    }],
  };
}

function groupBarOption(groups = []) {
  const visible = [...groups].slice(0, 10).reverse();
  return {
    color: ['#167c80'], animationDuration: 1000, animationEasing: 'quarticOut',
    grid: { left: 18, right: 24, top: 10, bottom: 20, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#edf1f3' } } },
    yAxis: { type: 'category', data: visible.map((item) => item.name), axisTick: { show: false }, axisLine: { show: false } },
    series: [{
      type: 'bar', data: visible.map((item) => item.value), barWidth: 14,
      itemStyle: { borderRadius: [0, 8, 8, 0] }, label: { show: true, position: 'right', color: '#415466' },
    }],
  };
}

function trendOption(trend = []) {
  return {
    color: ['#167c80', '#e07a3f'], animationDuration: 1100, animationEasing: 'cubicOut',
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 8, icon: 'roundRect' },
    grid: { left: 20, right: 18, top: 40, bottom: 16, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: trend.map((item) => dayjs(item.date).format('MM/DD')), axisLine: { lineStyle: { color: '#dce3e7' } } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#edf1f3' } } },
    series: [
      { name: '客户消息', type: 'line', smooth: true, symbolSize: 7, data: trend.map((item) => item.inbound), areaStyle: { opacity: 0.12 } },
      { name: '发送消息', type: 'line', smooth: true, symbolSize: 7, data: trend.map((item) => item.outbound), areaStyle: { opacity: 0.08 } },
    ],
  };
}

function profileBarOption(types = {}) {
  const entries = Object.entries(types);
  return {
    color: ['#2f5d8a', '#e07a3f'], animationDuration: 950,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, right: 8 },
    grid: { left: 18, right: 20, top: 40, bottom: 18, containLabel: true },
    xAxis: { type: 'category', data: entries.map(([name]) => labels[name] || name), axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#edf1f3' } } },
    series: [
      { name: '资料文件', type: 'bar', barMaxWidth: 28, data: entries.map(([, item]) => item.profiles), itemStyle: { borderRadius: [7, 7, 0, 0] } },
      { name: '客户数量', type: 'bar', barMaxWidth: 28, data: entries.map(([, item]) => item.targets), itemStyle: { borderRadius: [7, 7, 0, 0] } },
    ],
  };
}

function gaugeOption(value) {
  return {
    animationDuration: 1200,
    series: [{
      type: 'gauge', startAngle: 210, endAngle: -30, radius: '90%',
      progress: { show: true, width: 18, roundCap: true, itemStyle: { color: '#167c80' } },
      axisLine: { lineStyle: { width: 18, color: [[1, '#e9eff1']] } },
      pointer: { show: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      title: { offsetCenter: [0, '38%'], color: '#667684', fontSize: 13 },
      detail: { valueAnimation: true, formatter: '{value}%', offsetCenter: [0, '0%'], color: '#18364a', fontSize: 28, fontWeight: 800 },
      data: [{ value, name: '发送成功率' }],
    }],
  };
}

function Metric({ label, value, suffix, accent }) {
  return (
    <div className="dashboard-metric">
      <span>{label}</span>
      <strong style={{ color: accent }}>{numberFormatter.format(value || 0)}{suffix || ''}</strong>
    </div>
  );
}

function EChart({ option, style }) {
  return <ReactEChartsCore echarts={echarts} option={option} style={style} notMerge lazyUpdate />;
}

function SectionTitle({ icon, title, description, tag }) {
  return (
    <div className="dashboard-section-heading">
      <div className="dashboard-section-icon">{icon}</div>
      <div><Typography.Title level={4}>{title}</Typography.Title><Typography.Text type="secondary">{description}</Typography.Text></div>
      {tag ? <Tag>{tag}</Tag> : null}
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['dashboard-statistics'],
    queryFn: getDashboardStatistics,
    refetchInterval: 30000,
  });

  if (isLoading || !data) return <div className="page dashboard-page"><Skeleton active paragraph={{ rows: 14 }} /></div>;

  const taskColumns = [
    { title: '任务名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 120,
      render: (value) => <Tag>{labels[value] || value}</Tag>,
    },
    { title: '目标数', dataIndex: 'total_targets', key: 'total_targets', width: 110, render: (value) => numberFormatter.format(value || 0) },
    { title: '成功数', dataIndex: 'sent', key: 'sent', width: 110, render: (value) => <span className="dashboard-task-success">{numberFormatter.format(value || 0)}</span> },
    { title: '失败数', dataIndex: 'failed', key: 'failed', width: 110, render: (value) => <span className="dashboard-task-failed">{numberFormatter.format(value || 0)}</span> },
  ];

  const overviewCards = [
    { key: 'sessions', label: 'Session总数', value: data.overview.sessions, detail: `已连接 ${data.sessions.connected}`, icon: <UserOutlined />, tone: 'teal' },
    { key: 'conversations', label: '聊天客户', value: data.overview.conversations, detail: `未读消息 ${data.messages.unread}`, icon: <MessageOutlined />, tone: 'orange' },
    { key: 'materials', label: '素材总数', value: data.overview.materials, detail: `${data.materials.groups} 个素材分组`, icon: <AppstoreOutlined />, tone: 'blue' },
    { key: 'customer_targets', label: '客户资料数量', value: data.overview.customer_targets, detail: `${data.customer_profiles.total} 个资料文件`, icon: <ContactsOutlined />, tone: 'gold' },
    { key: 'tasks', label: '任务总数', value: data.overview.tasks, detail: `累计成功 ${data.tasks.sent}`, icon: <ProfileOutlined />, tone: 'red' },
  ];

  return (
    <div className="page dashboard-page">
      <div className="dashboard-hero">
        <div>
          <Typography.Text className="dashboard-eyebrow">TG MARKETING OVERVIEW</Typography.Text>
          <Typography.Title>业务控制面板</Typography.Title>
          <Typography.Text>聚合 Session、聊天、素材、客户资料与任务执行数据</Typography.Text>
        </div>
        <div className="dashboard-refresh">
          <span>更新时间 {dayjs(dataUpdatedAt).format('YYYY-MM-DD HH:mm:ss')}</span>
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>刷新数据</Button>
        </div>
      </div>

      <div className="dashboard-overview-grid">
        {overviewCards.map((item) => (
          <Card key={item.key} className={`dashboard-overview-card tone-${item.tone}`} bordered={false}>
            <div className="dashboard-overview-icon">{item.icon}</div>
            <div><span>{item.label}</span><strong>{numberFormatter.format(item.value || 0)}</strong><small>{item.detail}</small></div>
          </Card>
        ))}
      </div>

      <Card className="dashboard-section-card" bordered={false}>
        <SectionTitle icon={<UserOutlined />} title="Session 管理数据" description="连接质量、账号状态与分组规模" tag={`${data.sessions.connected}/${data.sessions.total} 在线`} />
        <div className="dashboard-metrics-row four">
          <Metric label="Session总数" value={data.sessions.total} accent="#167c80" />
          <Metric label="在线" value={data.sessions.connected} accent="#638b63" />
          <Metric label="不在线" value={data.sessions.offline} accent="#728197" />
          <Metric label="疑似/封禁" value={(data.sessions.bidirectional.restricted || 0) + (data.sessions.bidirectional.blocked || 0)} accent="#c94f5d" />
        </div>
        <div className="dashboard-chart-grid two">
          <div className="dashboard-chart"><h4>连接状态</h4><EChart option={pieOption(data.sessions.status, '连接状态')} style={{ height: 280 }} /></div>
          <div className="dashboard-chart"><h4>Session 分组规模</h4><EChart option={groupBarOption(data.sessions.groups)} style={{ height: 280 }} /></div>
        </div>
      </Card>

      <Card className="dashboard-section-card" bordered={false}>
        <SectionTitle icon={<MessageOutlined />} title="消息列表数据" description="客户会话、回复情况与近 7 日消息走势" tag={`今日 ${data.messages.today} 条`} />
        <div className="dashboard-metrics-row">
          <Metric label="全部聊天" value={data.messages.conversations} accent="#167c80" />
          <Metric label="收藏聊天" value={data.messages.favorites} accent="#d0a52b" />
          <Metric label="消息总数" value={data.messages.total} accent="#2f5d8a" />
          <Metric label="客户消息" value={data.messages.inbound} accent="#638b63" />
          <Metric label="未读消息" value={data.messages.unread} accent="#c94f5d" />
        </div>
        <div className="dashboard-chart-grid two-wide">
          <div className="dashboard-chart"><h4>近 7 日消息趋势</h4><EChart option={trendOption(data.messages.trend)} style={{ height: 290 }} /></div>
          <div className="dashboard-chart"><h4>客户回复状态</h4><EChart option={pieOption(data.messages.reply_status, '回复状态')} style={{ height: 290 }} /></div>
        </div>
      </Card>

      <div className="dashboard-section-pair">
        <Card className="dashboard-section-card" bordered={false}>
          <SectionTitle icon={<AppstoreOutlined />} title="素材库数据" description="素材类型与分组概览" />
          <div className="dashboard-metrics-row compact">
            <Metric label="素材总数" value={data.materials.total} accent="#167c80" />
            <Metric label="素材分组" value={data.materials.groups} accent="#e07a3f" />
          </div>
          <div className="dashboard-chart"><EChart option={pieOption(data.materials.types, '素材类型')} style={{ height: 280 }} /></div>
        </Card>
        <Card className="dashboard-section-card" bordered={false}>
          <SectionTitle icon={<ContactsOutlined />} title="客户资料数据" description="资料文件与可执行目标规模" />
          <div className="dashboard-metrics-row compact">
            <Metric label="资料文件" value={data.customer_profiles.total} accent="#2f5d8a" />
            <Metric label="客户数量" value={data.customer_profiles.total_targets} accent="#e07a3f" />
          </div>
          <div className="dashboard-chart"><EChart option={profileBarOption(data.customer_profiles.types)} style={{ height: 280 }} /></div>
        </Card>
      </div>

      <Card className="dashboard-section-card dashboard-task-section" bordered={false}>
        <SectionTitle icon={<ProfileOutlined />} title="任务管理数据" description="任务状态、发送进度与执行质量" tag={`${data.tasks.active} 个活跃任务`} />
        <div className="dashboard-metrics-row">
          <Metric label="任务总数" value={data.tasks.total} accent="#2f5d8a" />
          <Metric label="目标总数" value={data.tasks.total_targets} accent="#167c80" />
          <Metric label="发送成功" value={data.tasks.sent} accent="#638b63" />
          <Metric label="发送失败" value={data.tasks.failed} accent="#c94f5d" />
          <Metric label="等待处理" value={data.tasks.remaining} accent="#d0a52b" />
        </div>
        <div className="dashboard-chart-grid task-grid">
          <div className="dashboard-chart"><h4>任务状态分布</h4><EChart option={pieOption(data.tasks.status, '任务状态')} style={{ height: 300 }} /></div>
          <div className="dashboard-chart gauge-chart"><h4>任务发送质量</h4><EChart option={gaugeOption(data.tasks.success_rate)} style={{ height: 270 }} /></div>
          <div className="dashboard-progress-panel">
            <CheckCircleOutlined />
            <span>整体处理进度</span>
            <strong>{data.tasks.progress_rate}%</strong>
            <Progress percent={data.tasks.progress_rate} showInfo={false} strokeColor="#e07a3f" trailColor="#e9eff1" />
            <small>已处理 {numberFormatter.format(data.tasks.sent + data.tasks.failed)} / {numberFormatter.format(data.tasks.total_targets)}</small>
          </div>
        </div>
        <div className="dashboard-task-detail">
          <h4>各任务执行明细</h4>
          <Table
            rowKey="id"
            columns={taskColumns}
            dataSource={data.tasks.items || []}
            pagination={false}
            locale={{ emptyText: '暂无任务' }}
            scroll={{ x: 650, y: 420 }}
            size="middle"
          />
        </div>
      </Card>
    </div>
  );
}
