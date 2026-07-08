# TG营销管理系统

按 `readme.txt` 目录结构实现的 FastAPI + React 版本。

## 本地启动

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\uvicorn main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

访问：

- 前端：`http://127.0.0.1:5173`
- 后端文档：`http://127.0.0.1:8000/docs`

## 关键修复

Session 连接状态不实时更新的问题已通过后端 WebSocket 主动广播和前端 React Query 增量更新修复。

## 文档

- 部署说明：`deploy/README.md`
- 代码审查：`docs/code-review.md`
- 技术需求文档：`docs/technical-requirements.md`
