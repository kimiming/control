import { ClearOutlined, PaperClipOutlined, SendOutlined, SearchOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Avatar, Badge, Button, Card, Empty, Image, Input, List, Popover, Radio, Select, Space, Tabs, Tag, Tooltip, Typography, message } from 'antd';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useMemo, useRef, useState } from 'react';
import { FixedSizeList as VirtualList } from 'react-window';

import { getConversationCounts, getConversations, getCustomerMessages, getMaterials, getSupportAgents, replyCustomer, updateCustomerFavorite } from '../api/index.js';

const statusColor = {
  success: 'green',
  pending: 'default',
  sending: 'blue',
  failed: 'red',
  not_replied: 'default',
  replied: 'green',
};

const statusText = {
  success: '发送成功',
  pending: '待发送',
  sending: '发送中',
  failed: '发送失败',
  unknown: '未知',
  not_replied: '未回复',
  replied: '已回复',
  connected: '已连接',
  disconnected: '未连接',
  connecting: '连接中',
  error: '异常',
};

const materialTypeMeta = {
  text: { label: '文字', color: 'blue' },
  image: { label: '图片', color: 'green' },
  contact: { label: '名片', color: 'purple' },
};

const conversationIdentity = (customer) => {
  const sessionId = customer.assigned_session_id ?? 'unassigned';
  const telegramIdentity = customer.tg_id
    || customer.username?.trim().toLowerCase()
    || customer.phone_number?.trim();
  return telegramIdentity ? `${sessionId}:${telegramIdentity}` : `customer:${customer.id}`;
};

export default function Messages() {
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [selected, setSelected] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [materialId, setMaterialId] = useState();
  const [materialType, setMaterialType] = useState('text');
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const [kfId, setKfId] = useState();
  const [replyStatus, setReplyStatus] = useState();
  const [chatTab, setChatTab] = useState('all');
  const customerListRef = useRef(null);
  const chatMessagesRef = useRef(null);
  const [customerListHeight, setCustomerListHeight] = useState(400);

  const { data: agents = [] } = useQuery({
    queryKey: ['support-agents'],
    queryFn: getSupportAgents,
  });
  const { data: materials = [] } = useQuery({
    queryKey: ['materials', 'messages'],
    queryFn: () => getMaterials(),
  });

  const conversationFilterParams = useMemo(() => {
    const params = {};
    if (keyword) params.keyword = keyword;
    if (kfId) params.kf_id = kfId;
    if (replyStatus) params.reply_status = replyStatus;
    return params;
  }, [keyword, kfId, replyStatus]);

  const customerParams = useMemo(() => {
    const params = { ...conversationFilterParams };
    if (chatTab === 'favorites') params.is_favorite = true;
    return params;
  }, [conversationFilterParams, chatTab]);

  const { data: conversationCounts = { all: 0, favorites: 0 } } = useQuery({
    queryKey: ['customers', 'conversation-counts', conversationFilterParams],
    queryFn: () => getConversationCounts(conversationFilterParams),
    refetchInterval: 5000,
  });

  const customerQuery = useInfiniteQuery({
    queryKey: ['customers', customerParams],
    queryFn: ({ pageParam }) => getConversations({ ...customerParams, page: pageParam, page_size: 20 }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.page + 1 : undefined,
    refetchInterval: 5000,
  });
  const customers = useMemo(() => {
    const seen = new Set();
    return (customerQuery.data?.pages || []).flatMap((page) => page.items || []).filter((item) => {
      const identity = conversationIdentity(item);
      if (seen.has(identity)) return false;
      seen.add(identity);
      return true;
    });
  }, [customerQuery.data]);

  const selectedCustomer = useMemo(
    () => customers.find((item) => item.id === selected?.id) || selected,
    [customers, selected],
  );
  const selectedMaterial = useMemo(
    () => materials.find((item) => item.id === materialId),
    [materials, materialId],
  );

  const messageQuery = useInfiniteQuery({
    queryKey: ['customer-messages', selectedCustomer?.id],
    queryFn: ({ pageParam }) => getCustomerMessages(selectedCustomer.id, { page_size: 20, before_id: pageParam || undefined }),
    initialPageParam: null,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.next_before_id : undefined,
    enabled: Boolean(selectedCustomer?.id),
    refetchInterval: (query) => selectedCustomer?.id && query.state.fetchStatus !== 'fetching' ? 10000 : false,
  });
  const messages = useMemo(() => {
    const seen = new Set();
    return [...(messageQuery.data?.pages || [])].reverse().flatMap((page) => page.items || []).filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }, [messageQuery.data]);

  useEffect(() => {
    const element = customerListRef.current;
    if (!element) return undefined;
    const updateHeight = () => setCustomerListHeight(Math.max(element.clientHeight, 120));
    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = chatMessagesRef.current;
    if (!element || !selectedCustomer?.id) return;
    requestAnimationFrame(() => { element.scrollTop = element.scrollHeight; });
  }, [selectedCustomer?.id]);

  const loadOlderMessages = async (event) => {
    const element = event.currentTarget;
    if (element.scrollTop > 60 || !messageQuery.hasNextPage || messageQuery.isFetchingNextPage) return;
    const oldHeight = element.scrollHeight;
    await messageQuery.fetchNextPage();
    requestAnimationFrame(() => { element.scrollTop = element.scrollHeight - oldHeight; });
  };

  const replyMutation = useMutation({
    mutationFn: () => replyCustomer(selectedCustomer.id, { text: replyText.trim() || undefined, material_id: materialId }),
    onSuccess: () => {
      setReplyText('');
      setMaterialId(undefined);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['customer-messages', selectedCustomer.id] });
      message.success('回复已发送');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const favoriteMutation = useMutation({
    mutationFn: ({ id, isFavorite }) => updateCustomerFavorite(id, isFavorite),
    onSuccess: (customer) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      if (selectedCustomer?.id === customer.id) {
        setSelected(chatTab === 'favorites' && !customer.is_favorite ? null : customer);
      }
      message.success(customer.is_favorite ? '已收藏为意向用户' : '已取消收藏');
    },
    onError: (error) => message.error(error?.response?.data?.detail || error.message),
  });

  const toggleFavorite = (customer, event) => {
    event?.stopPropagation();
    favoriteMutation.mutate({ id: customer.id, isFavorite: !customer.is_favorite });
  };

  const agentOptions = [
    { label: '全部客服', value: 0 },
    ...agents.map((item) => ({ label: `${item.name} (${item.session_count})`, value: item.id })),
  ];
  const materialOptions = materials.map((item) => ({
    value: item.id,
    label: `${item.name}（${materialTypeMeta[item.material_type]?.label || item.material_type}）`,
  }));
  const filteredMaterialOptions = materialOptions.filter((option) => {
    const material = materials.find((item) => item.id === option.value);
    return material?.material_type === materialType;
  });

  const renderMaterialOption = (option) => {
    const material = materials.find((item) => item.id === option.value);
    return (
      <Space>
        <Tag color={materialTypeMeta[material?.material_type]?.color || 'default'}>
          {materialTypeMeta[material?.material_type]?.label || material?.material_type}
        </Tag>
        <span>{material?.name || option.label}</span>
      </Space>
    );
  };

  const renderMaterialPreview = () => {
    if (!selectedMaterial) return null;
    const meta = materialTypeMeta[selectedMaterial.material_type] || {};
    let contact = null;
    if (selectedMaterial.material_type === 'contact') {
      try {
        contact = JSON.parse(selectedMaterial.content || '{}');
      } catch {
        contact = {};
      }
    }
    return (
      <div className="chat-material-preview">
        <Space align="start">
          <Tag color={meta.color || 'default'}>{meta.label || selectedMaterial.material_type}</Tag>
          <Space direction="vertical" size={2} style={{ minWidth: 0 }}>
            <Typography.Text strong ellipsis>{selectedMaterial.name}</Typography.Text>
            {selectedMaterial.material_type === 'image' && selectedMaterial.file_path ? (
              <Image src={selectedMaterial.file_path} width={72} height={54} style={{ objectFit: 'cover', borderRadius: 8 }} />
            ) : null}
            {selectedMaterial.material_type === 'text' ? (
              <Typography.Text type="secondary" ellipsis>{selectedMaterial.content || '-'}</Typography.Text>
            ) : null}
            {selectedMaterial.material_type === 'contact' ? (
              <Typography.Text type="secondary" ellipsis>
                {`${contact?.first_name || ''} ${contact?.last_name || ''} ${contact?.phone_number || ''}`.trim() || '名片'}
              </Typography.Text>
            ) : null}
          </Space>
        </Space>
        <Tooltip title="移除素材">
          <Button icon={<ClearOutlined />} onClick={() => setMaterialId(undefined)} />
        </Tooltip>
      </div>
    );
  };

  const materialPicker = (
    <Space direction="vertical" size={10} className="chat-material-picker">
      <Radio.Group
        optionType="button"
        buttonStyle="solid"
        value={materialType}
        onChange={(event) => {
          setMaterialType(event.target.value);
          setMaterialId(undefined);
        }}
        options={[
          { label: '文字', value: 'text' },
          { label: '图片', value: 'image' },
          { label: '名片', value: 'contact' },
        ]}
      />
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder={`选择${materialTypeMeta[materialType]?.label || ''}素材`}
        value={selectedMaterial?.material_type === materialType ? materialId : undefined}
        options={filteredMaterialOptions}
        optionRender={renderMaterialOption}
        onChange={(value) => {
          setMaterialId(value);
          if (value) setMaterialPickerOpen(false);
        }}
      />
    </Space>
  );

  return (
    <div className="page customer-workbench">
      <aside className="customer-sidebar">
        <Select
          value={kfId || 0}
          options={agentOptions}
          onChange={(value) => {
            setKfId(value || undefined);
            setSelected(null);
          }}
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索手机号、用户名、昵称、TG ID"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <Select
          allowClear
          placeholder="筛选客户回复状态"
          value={replyStatus}
          options={[
            { label: '已回复客户', value: 'replied' },
            { label: '未回复客户', value: 'not_replied' },
            { label: '对方已读未回复（✓✓）', value: 'peer_read' },
            { label: '对方未读未回复（✓）', value: 'peer_unread' },
          ]}
          onChange={(value) => {
            setReplyStatus(value);
            setSelected(null);
          }}
        />
        <Tabs
          className="chat-list-tabs"
          activeKey={chatTab}
          onChange={(value) => {
            setChatTab(value);
            setSelected(null);
          }}
          items={[
            { key: 'all', label: `全部聊天（${conversationCounts.all}）` },
            { key: 'favorites', label: `收藏聊天（${conversationCounts.favorites}）` },
          ]}
        />
        <div className="customer-virtual-list" ref={customerListRef}>
          <VirtualList
            height={customerListHeight}
            width="100%"
            itemCount={customers.length}
            itemSize={154}
            itemData={customers}
            onItemsRendered={({ visibleStopIndex }) => {
              if (visibleStopIndex >= customers.length - 3 && customerQuery.hasNextPage && !customerQuery.isFetchingNextPage) {
                customerQuery.fetchNextPage();
              }
            }}
          >
            {({ index, style, data }) => {
              const item = data[index];
              return (
            <div className="customer-virtual-row" style={style}>
            <List.Item
              className={selectedCustomer?.id === item.id ? 'customer-list-item active' : 'customer-list-item'}
              onClick={() => setSelected(item)}
            >
              <Card
                className="customer-card"
                size="small"
                bordered
                styles={{ body: { padding: 12 } }}
              >
                <List.Item.Meta
                  avatar={
                    <Badge count={item.unread_count || 0} size="small" offset={[-2, 2]}>
                      <Avatar src={item.avatar}>{(item.nickname || item.username || item.phone_number)?.[0]}</Avatar>
                    </Badge>
                  }
                  title={
                    <div className="customer-card-title">
                      <Space size={6}>
                        <Typography.Text strong ellipsis>{item.nickname || item.username || item.phone_number}</Typography.Text>
                        <Tag color={statusColor[item.reply_status]}>{statusText[item.reply_status] || item.reply_status}</Tag>
                      </Space>
                      <Tooltip title={item.is_favorite ? '取消收藏' : '收藏为意向用户'}>
                        <Button
                          type="text"
                          className={item.is_favorite ? 'favorite-button active' : 'favorite-button'}
                          icon={item.is_favorite ? <StarFilled /> : <StarOutlined />}
                          loading={favoriteMutation.isPending && favoriteMutation.variables?.id === item.id}
                          onClick={(event) => toggleFavorite(item, event)}
                        />
                      </Tooltip>
                    </div>
                  }
                  description={
                    <Space direction="vertical" size={0}>
                      <Typography.Text type="secondary">{item.username || item.phone_number || '-'}</Typography.Text>
                      <Typography.Text type="secondary">客服 {item.kf_name || '未绑定'}</Typography.Text>
                      <Typography.Text type="secondary">来自 {item.assigned_session_name || '-'}</Typography.Text>
                    </Space>
                  }
                />
              </Card>
            </List.Item>
            </div>
              );
            }}
          </VirtualList>
          {customerQuery.isLoading ? <div className="customer-list-status">正在加载会话…</div> : null}
          {customerQuery.isFetchingNextPage ? <div className="customer-list-status">正在加载更多…</div> : null}
          {!customerQuery.isLoading && !customers.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" /> : null}
        </div>
      </aside>

      <main className="chat-panel">
        {selectedCustomer ? (
          <>
            <div className="chat-header">
              <div>
                <Typography.Title level={4}>{selectedCustomer.nickname || selectedCustomer.username || selectedCustomer.phone_number}</Typography.Title>
                <Typography.Text type="secondary">
                  客服: {selectedCustomer.kf_name || '未绑定'} / Session: {selectedCustomer.assigned_session_name || '-'}
                </Typography.Text>
              </div>
              <Tooltip title={selectedCustomer.is_favorite ? '取消收藏' : '收藏为意向用户'}>
                <Button
                  className={selectedCustomer.is_favorite ? 'favorite-button active' : 'favorite-button'}
                  icon={selectedCustomer.is_favorite ? <StarFilled /> : <StarOutlined />}
                  onClick={(event) => toggleFavorite(selectedCustomer, event)}
                >
                  {selectedCustomer.is_favorite ? '已收藏' : '收藏意向用户'}
                </Button>
              </Tooltip>
            </div>
            <div className="chat-messages" ref={chatMessagesRef} onScroll={loadOlderMessages}>
              {messageQuery.isFetchingNextPage ? <div className="chat-history-status">正在加载更早消息…</div> : null}
              {!messageQuery.hasNextPage && messages.length ? <div className="chat-history-status">已经到最早的消息</div> : null}
              {messages.length ? messages.map((item) => (
                <div key={item.id} className={item.direction === 'outbound' ? 'chat-bubble outbound' : 'chat-bubble inbound'}>
                  {item.image_path ? (
                    <Image
                      className="chat-image"
                      src={item.image_path}
                      width={180}
                      preview={{ src: item.image_path }}
                    />
                  ) : null}
                  {item.content ? <div>{item.content}</div> : null}
                  <div className="chat-message-meta">
                    <span>{dayjs(item.created_at).format('YYYY-MM-DD HH:mm:ss')}</span>
                    {item.direction === 'outbound' ? (
                      <Tooltip title={item.read_status === 'read' ? '对方已读' : '已发送'}>
                        <span className={item.read_status === 'read' ? 'message-checks read' : 'message-checks'}>
                          {item.read_status === 'read' ? '✓✓' : '✓'}
                        </span>
                      </Tooltip>
                    ) : null}
                  </div>
                </div>
              )) : <Empty description="暂无消息" />}
            </div>
            <div className="chat-composer">
              <div className="chat-composer-fields">
                {renderMaterialPreview()}
                <Input.TextArea
                  rows={3}
                  value={replyText}
                  placeholder={selectedMaterial?.material_type === 'image' ? '可填写图片说明文字' : '输入回复文字'}
                  onChange={(event) => setReplyText(event.target.value)}
                />
              </div>
              <Tooltip title="选择素材库素材">
                <Popover
                  trigger="click"
                  open={materialPickerOpen}
                  onOpenChange={setMaterialPickerOpen}
                  content={materialPicker}
                  placement="topRight"
                >
                  <Button icon={<PaperClipOutlined />} />
                </Popover>
              </Tooltip>
              <Button
                type="primary"
                icon={<SendOutlined />}
                disabled={!replyText.trim() && !materialId}
                loading={replyMutation.isPending}
                onClick={() => replyMutation.mutate()}
              >
                发送
              </Button>
            </div>
          </>
        ) : <Empty description="请选择客户会话" />}
      </main>

      <aside className="customer-detail">
        {selectedCustomer ? (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Typography.Title level={5}>客户资料</Typography.Title>
            <div className="customer-info-card"><Typography.Text type="secondary">用户名</Typography.Text><strong>{selectedCustomer.username || '-'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">手机号</Typography.Text><strong>{selectedCustomer.phone_number || '-'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">TG ID</Typography.Text><strong>{selectedCustomer.tg_id || '-'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">负责客服</Typography.Text><strong>{selectedCustomer.kf_name || '未绑定'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">意向收藏</Typography.Text><strong>{selectedCustomer.is_favorite ? '已收藏' : '未收藏'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">发送状态</Typography.Text><Tag color={statusColor[selectedCustomer.send_status]}>{statusText[selectedCustomer.send_status] || selectedCustomer.send_status}</Tag></div>
            <div className="customer-info-card"><Typography.Text type="secondary">回复状态</Typography.Text><Tag color={statusColor[selectedCustomer.reply_status]}>{statusText[selectedCustomer.reply_status] || selectedCustomer.reply_status}</Tag></div>
            <div className="customer-info-card"><Typography.Text type="secondary">所属 Session</Typography.Text><strong>{selectedCustomer.assigned_session_name || '-'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">Session 状态</Typography.Text><strong>{statusText[selectedCustomer.assigned_session_status] || selectedCustomer.assigned_session_status || '-'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">最近消息</Typography.Text><strong>{selectedCustomer.last_message_at ? dayjs(selectedCustomer.last_message_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</strong></div>
            <div className="customer-info-card"><Typography.Text type="secondary">备注</Typography.Text><strong>{selectedCustomer.remark || '-'}</strong></div>
          </Space>
        ) : <Empty description="无客户资料" />}
      </aside>
    </div>
  );
}
