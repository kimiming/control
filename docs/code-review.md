# TG营销管理系统代码质量与安全审查报告

审查范围：

- `backend/app/api/*.py`
- `backend/app/services/*.py`
- `frontend/src/pages/*.jsx`
- `frontend/src/api/index.js`

## 结论

当前代码已经实现 Session 管理、WebSocket 实时状态推送、批量导入、分组、健康检查、日志、消息分页和虚拟滚动的基础能力。主要风险集中在认证授权缺失、TG Session 安全存储不足、生产级迁移体系缺失、日志审计字段不完整。

## 1. API接口安全性

现状：

- FastAPI 接口尚未接入认证和授权。
- Pydantic schema 已对主要字段做长度和枚举校验。
- 文件导入接口限制了前端 accept，但后端未严格校验 MIME、扩展名和文件大小。

风险：

- 未登录用户可调用连接、删除、导入、健康检查等高危接口。
- 批量导入大文件可能造成内存压力。

建议：

- 增加 JWT/OAuth2 登录认证，并为 Session 删除、导入、连接操作增加 RBAC 权限。
- 后端限制上传文件大小，例如 Nginx `client_max_body_size 10m`，FastAPI 层校验扩展名和行数。
- WebSocket 增加 token 校验：`/ws/sessions/all?token=...`。

## 2. 数据库操作

现状：

- 使用 SQLAlchemy ORM 查询，SQL 注入风险较低。
- 已添加常用索引：`sessions.status/group_id`、`messages.session_id/created_at`、`session_logs.session_id/created_at`。
- 部分服务方法在循环中多次 commit。

风险：

- 健康检查批量循环中每个 Session 单独提交，数量大时性能差。
- 当前使用 `Base.metadata.create_all` 初始化，生产环境缺少 Alembic 迁移版本管理。

建议：

- 引入 Alembic 管理数据库结构变更。
- 健康检查可批量 flush/commit，并限制并发。
- 对列表接口增加分页、排序字段白名单和过滤条件。

## 3. TG账号安全

现状：

- 当前实现保存 Telethon session 文件名，session 文件挂载到 `SESSION_DIR`。
- 未实现 `session_string` 加密存储。

风险：

- 服务器磁盘泄漏会导致 TG 账号被接管。
- 日志中可能记录连接失败原因，需避免包含敏感验证码、session 字符串。

建议：

- 使用 Fernet/AES-GCM 加密 session_string，密钥放入环境变量或 KMS。
- session 文件目录权限设置为 `700`，运行用户独占。
- 增加敏感日志脱敏函数。

## 4. 错误处理与日志

现状：

- 服务层捕获了连接和健康检查异常，并写入 `session_logs`。
- API 层对不存在资源返回 404。

风险：

- 缺少结构化应用日志，无法按 request_id 追踪。
- 部分异常直接把原始错误写到数据库和前端。

建议：

- 使用 Python `logging` JSON formatter，记录 request_id、operator、ip。
- 前端展示通用错误，详细错误只进入服务端日志。
- `SessionLog.operator` 应从认证上下文写入。

## 5. 代码规范

现状：

- 后端结构清晰，API、service、model 分层基本合理。
- 前端页面和组件已拆分，Session 表格、弹窗独立。

建议：

- 后端加入 `ruff`、`black`、`mypy`。
- 前端加入 ESLint 配置和 `npm run lint` CI。
- API schema 建议继续集中在 `backend/app/schemas/`。

## 6. 性能问题

现状：

- Session 页面已从 5 秒轮询改为单 WebSocket 增量更新。
- 消息页面使用分页和 `react-window` 虚拟滚动。
- WebSocket manager 做了基础连接池和失效连接清理。

风险：

- WebSocket manager 是单进程内存态，多 worker 或多实例部署时无法跨进程广播。
- Redis cache 文件已提供，但列表接口尚未强制使用缓存，避免状态推送和缓存失效不一致。

建议：

- 多进程部署时使用 Redis Pub/Sub 做 WebSocket 广播。
- Session 列表可按 `updated_at` 增量拉取，接口支持 `since`。
- 消息列表使用 keyset pagination：`created_at < cursor`，避免深分页 offset 性能下降。

## 实时状态问题原因与修复

原因：

- 后端 `connect_session` 连接成功后只更新数据库，未主动推送状态。
- 前端依赖 `useQuery` 初次加载或轮询，WebSocket 消息未写入 Query Cache。
- 如果每个 Session 单独连接 WebSocket，连接数量会随列表增长导致服务器压力上升。

已修复：

- `session_service.connect_session` 在进入 `connecting` 和最终 `connected/error` 后调用 `publish_status`。
- `websocket_manager.py` 支持按 Session 或全局 `*` 广播。
- `Sessions.jsx` 建立单个 `/ws/sessions/all` 连接，收到消息后通过 `queryClient.setQueryData(['sessions'], ...)` 增量更新。

## 高优先级整改清单

1. 增加认证授权和 WebSocket token 校验。
2. 加密 TG session_string 或严格保护 session 文件目录。
3. 引入 Alembic，停止生产环境依赖 `create_all`。
4. 导入接口增加文件大小、行数、扩展名校验。
5. 多实例部署时把 WebSocket 广播切换到 Redis Pub/Sub。
