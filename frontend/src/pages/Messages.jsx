import { useInfiniteQuery } from '@tanstack/react-query';
import { Button, Spin } from 'antd';
import { FixedSizeList as List } from 'react-window';
import { getMessages } from '../api/index.js';

export default function Messages() {
  const query = useInfiniteQuery({
    queryKey: ['messages'],
    queryFn: ({ pageParam = 1 }) => getMessages({ page: pageParam, page_size: 100 }),
    getNextPageParam: (lastPage, pages) => (lastPage.length === 100 ? pages.length + 1 : undefined),
  });

  const messages = query.data?.pages.flat() || [];

  const Row = ({ index, style }) => {
    const item = messages[index];
    if (!item) return null;
    return (
      <div className="message-row" style={style}>
        <span>{item.created_at}</span>
        <span>{item.sender || item.chat_id}</span>
        <span>{item.content}</span>
      </div>
    );
  };

  return (
    <div className="page">
      <div className="toolbar">
        <Button onClick={() => query.fetchNextPage()} disabled={!query.hasNextPage} loading={query.isFetchingNextPage}>
          加载更多
        </Button>
      </div>
      {query.isLoading ? <Spin /> : (
        <div className="message-list">
          <List height={680} itemCount={messages.length} itemSize={44} width="100%">
            {Row}
          </List>
        </div>
      )}
    </div>
  );
}
