import { Alert, Card, Col, Divider, Row, Space, Steps, Tag, Typography } from 'antd';

const modules = [
  {
    key: 'sessions',
    title: 'Session管理',
    color: 'blue',
    features: [
      '新增、编辑、删除 Session 账号记录。',
      '导入 .session 文件，或导入 txt / csv / xlsx 账号清单。',
      '批量连接、批量断开、健康检测、批量双向号检测。',
      '创建分组并把 Session 批量移动到指定分组。',
      '把 Session 批量移动到客服或代理。',
      '查看连接状态、健康状态、双向号状态、已发送数量、通讯录数量。',
      '识别通讯录、导入通讯录、清空通讯录。',
      '查看 Session 操作日志和任务发送日志。',
    ],
    usage: [
      '先导入已有 Session 文件，或先导入账号清单建立记录。',
      '给 Session 配好分组、代理和客服归属。',
      '先做批量连接，再做健康检测，确认账号和代理能正常连上 Telegram。',
      '如果需要检查账号限制情况，再执行双向号检测。',
      '如果后续要用联系人作为发送目标，可以先识别或导入通讯录。',
    ],
  },
  {
    key: 'messages',
    title: '消息列表',
    color: 'cyan',
    features: [
      '集中查看客户会话列表和聊天记录。',
      '支持按关键字、客服、回复状态、收藏状态筛选客户。',
      '支持客户收藏，方便标记意向用户。',
      '支持发送文字回复。',
      '支持从素材库选择文字、图片、名片直接回复。',
      '会定时刷新客户列表和聊天记录，适合做客服工作台。',
    ],
    usage: [
      '先在 Session 管理中把 Session 绑定到客服。',
      '进入消息列表后，左侧先筛选客服或关键字，再选中一个客户会话。',
      '中间区域查看历史消息，底部输入框用于直接回复。',
      '需要快速发送标准话术时，先选素材类型，再选择素材发送。',
      '对重点客户可点星标收藏，后续在“收藏”视图里集中跟进。',
    ],
  },
  {
    key: 'customers',
    title: '客服管理',
    color: 'gold',
    features: [
      '创建客服账号标签，用于给 Session 归属客服。',
      '支持设置客服名称、颜色、状态、备注。',
      '支持按 Session 分组批量绑定客服。',
      '可查看每个客服当前绑定了哪些分组、多少个 Session。',
    ],
    usage: [
      '先想清楚你的客服分工，例如按业务线、按地区、按项目分配。',
      '创建客服时，直接选择要绑定的 Session 分组。',
      '绑定后，该分组下的 Session 会自动归属到这个客服名下。',
      '后续在消息列表中，就可以按客服维度筛选客户会话。',
    ],
  },
  {
    key: 'customer-profiles',
    title: '客户资料管理',
    color: 'purple',
    features: [
      '保存可复用的客户目标池。',
      '支持手机号资料和用户名资料两种类型。',
      '上传 TXT 后自动解析、去重并统计数量。',
      '支持查看、编辑、删除客户资料。',
      '任务创建时可以直接选择客户资料作为目标来源。',
    ],
    usage: [
      '把长期复用的目标客户整理成 TXT 文件后上传到这里。',
      '如果目标是手机号，就选择“手机号”；如果目标是 TG 用户名，就选择“用户名”。',
      '后续创建任务时直接选客户资料，不需要每次重复上传目标文件。',
      '适合按国家、渠道、活动主题维护多份客户池。',
    ],
  },
  {
    key: 'materials',
    title: '素材库管理',
    color: 'green',
    features: [
      '维护文字、图片、名片三类素材。',
      '支持素材分组、分组编辑、分组删除。',
      '支持单条新增，也支持批量导入文字和图片素材。',
      '支持设置优先级和备注。',
      '任务发送和客服回复都可以复用这里的素材。',
    ],
    usage: [
      '先建立素材分组，例如首触达话术、二次跟进话术、产品图、客服名片。',
      '文字素材适合存标准话术，图片素材适合发产品图或海报，名片素材适合发 TG 联系卡。',
      '给重要话术设置更高优先级，后续随机发送时更容易被选中。',
      '需要批量整理话术时，可先导入文字素材，再按分组归类。',
    ],
  },
  {
    key: 'tasks',
    title: '任务管理',
    color: 'red',
    features: [
      '创建、编辑、删除营销发送任务。',
      '支持单项发送、组合发送、拼接发送三种素材发送方式。',
      '支持手动导入 TXT、选择客户资料、使用通讯录联系人作为任务目标。',
      '支持手机号和用户名两种目标类型。',
      '支持设置每个 Session 的发送条数和发送时间间隔。',
      '支持执行、暂停、继续、取消、重试未发送任务。',
      '支持查看任务详情、活跃 Session、发送日志和剩余未发客户导出。',
    ],
    usage: [
      '先确认可用 Session 已连接，代理正常，素材和客户资料已准备好。',
      '创建任务时先确定发送方式，再选择文字、图片、名片或素材分组。',
      '如果是正式群发，建议先拿少量目标做测试任务，确认链路没问题再扩大规模。',
      '执行后进入日志查看发送结果，失败较多时优先检查代理、账号限制和目标格式。',
    ],
  },
  {
    key: 'proxies',
    title: '代理管理',
    color: 'orange',
    features: [
      '新增、编辑、删除代理。',
      '支持 HTTP、HTTPS、SOCKS4、SOCKS5。',
      '支持设置代理认证信息。',
      '支持给代理分配 Session 分组。',
      '支持测试代理可连通性和启用/停用代理。',
      'Session 在连接和任务发送时会使用所属代理。',
    ],
    usage: [
      '先录入代理地址、端口、认证信息和标签颜色。',
      '给代理绑定对应的 Session 分组，方便批量管理。',
      '保存后先做一次代理测试，确认端口可连接。',
      '再回到 Session 管理做连接和健康检测，确认代理实际能带账号正常连上 Telegram。',
    ],
  },
];

const flowSteps = [
  '导入 Session 或导入账号清单。',
  '创建代理并分配给对应 Session 分组。',
  '批量连接 Session，执行健康检测和双向号检测。',
  '创建 Session 分组并整理账号归属。',
  '创建客服并把分组或 Session 分配给客服。',
  '创建文字、图片、名片素材和素材分组。',
  '导入客户资料，整理手机号或用户名目标池。',
  '创建任务，选择 Session、目标和素材。',
  '执行任务并在消息列表、任务日志中跟踪效果。',
];

const caseSteps = [
  '先进入 Session管理，导入一批 Session 号或 .session 文件。',
  '进入 代理管理，创建代理并分配给对应的 Session 分组。',
  '回到 Session管理，批量选中账号后执行“批量连接”。',
  '连接成功后执行“健康检测”，确认 Session 和代理链路正常。',
  '在 Session管理 里创建分组，把这批账号移动到目标分组。',
  '进入 客服管理，创建客服，例如“客服A”，并绑定刚才的 Session 分组。',
  '进入 素材库管理，创建素材分组并录入首触达话术、图片或名片。',
  '进入 客户资料管理，上传目标客户 TXT，形成一个客户资料池。',
  '进入 任务管理，创建任务，选择刚才的 Session 分组、目标客户资料和发送素材。',
  '确认任务参数后执行任务，再根据发送日志和消息列表继续跟进。',
];

const cardStyle = { height: '100%' };

export default function UsageDocs() {
  return (
    <div className="page">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              TG营销管理系统使用文档
            </Typography.Title>
            <Typography.Paragraph style={{ margin: 0 }}>
              这份文档用于说明系统的主要功能、各页面的用途和推荐使用顺序。
            </Typography.Paragraph>
            <Space wrap size={[8, 8]}>
              {modules.map((module) => (
                <Tag key={module.key} color={module.color}>
                  {module.title}
                </Tag>
              ))}
            </Space>
          </Space>
        </Card>

        <Alert
          type="info"
          showIcon
          message="推荐原则"
          description="先整理账号和代理，再做连接与检测；先准备素材和客户资料，再创建任务；先小范围测试，再正式批量执行。"
        />

        <Row gutter={[16, 16]}>
          {modules.map((module) => (
            <Col key={module.key} xs={24} xl={12}>
              <Card title={module.title} extra={<Tag color={module.color}>功能说明</Tag>} style={cardStyle}>
                <Typography.Text strong>这个页面有什么功能</Typography.Text>
                <ul>
                  {module.features.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <Divider style={{ margin: '14px 0' }} />
                <Typography.Text strong>这个页面怎么使用</Typography.Text>
                <ul>
                  {module.usage.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </Card>
            </Col>
          ))}
        </Row>

        <Card title="系统总流程">
          <Steps
            direction="vertical"
            current={flowSteps.length - 1}
            items={flowSteps.map((item) => ({ title: item }))}
          />
        </Card>

        <Card title="完整案例">
          <Typography.Paragraph>
            下面是一个典型使用案例，适合第一次搭建一条完整营销链路时参考：
          </Typography.Paragraph>
          <ol>
            {caseSteps.map((item) => (
              <li key={item}>
                <Typography.Paragraph style={{ marginBottom: 8 }}>{item}</Typography.Paragraph>
              </li>
            ))}
          </ol>
        </Card>

        <Card title="使用建议">
          <ul style={{ marginBottom: 0 }}>
            <li>Session 连接成功不代表一定能稳定发送，正式跑任务前仍建议先做少量测试。</li>
            <li>代理测试通过，只代表端口可连接；真正是否适合 Telegram，还需要结合健康检测和小批量发送验证。</li>
            <li>客户资料和素材尽量按业务主题、地区、语言拆分，后续复用会更清晰。</li>
            <li>任务执行过程中，优先关注任务日志、失败原因和消息列表中的客户反馈。</li>
          </ul>
        </Card>
      </Space>
    </div>
  );
}
