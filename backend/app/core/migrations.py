from sqlalchemy import text

from app.core.auth import ensure_default_users
from app.core.database import SessionLocal, engine


def run_lightweight_migrations() -> None:
    if not engine.url.drivername.startswith("mysql"):
        return
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
          id INT AUTO_INCREMENT PRIMARY KEY,
          username VARCHAR(100) NOT NULL UNIQUE,
          password_hash VARCHAR(255) NOT NULL,
          role VARCHAR(30) NOT NULL DEFAULT 'user',
          status VARCHAR(30) NOT NULL DEFAULT 'active',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          INDEX ix_users_username (username),
          INDEX ix_users_role (role),
          INDEX ix_users_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS support_agents (
          id INT AUTO_INCREMENT PRIMARY KEY,
          name VARCHAR(100) NOT NULL UNIQUE,
          remark TEXT NULL,
          color VARCHAR(20) NOT NULL DEFAULT 'blue',
          status VARCHAR(30) NOT NULL DEFAULT 'active',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          INDEX ix_support_agents_name (name),
          INDEX ix_support_agents_status (status),
          INDEX ix_support_agents_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS customer_profiles (
          id INT AUTO_INCREMENT PRIMARY KEY,
          name VARCHAR(150) NOT NULL,
          content TEXT NOT NULL,
          total_count INT NOT NULL DEFAULT 0,
          remark TEXT NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          INDEX ix_customer_profiles_name (name),
          INDEX ix_customer_profiles_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        "ALTER TABLE support_agents ADD COLUMN color VARCHAR(20) NOT NULL DEFAULT 'blue'",
        "ALTER TABLE session_groups ADD COLUMN color VARCHAR(20) NOT NULL DEFAULT 'blue'",
        "ALTER TABLE sessions ADD COLUMN kf_id INT NULL",
        "CREATE INDEX ix_sessions_kf_id ON sessions (kf_id)",
        "CREATE INDEX ix_sessions_kf_status ON sessions (kf_id, status)",
        "ALTER TABLE sessions ADD CONSTRAINT fk_sessions_support_agent FOREIGN KEY (kf_id) REFERENCES support_agents(id) ON DELETE SET NULL",
        "ALTER TABLE messages ADD COLUMN direction VARCHAR(20) NOT NULL DEFAULT 'inbound'",
        "ALTER TABLE messages ADD COLUMN read_status VARCHAR(20) NOT NULL DEFAULT 'unread'",
        "ALTER TABLE messages ADD COLUMN telegram_message_id INT NULL",
        "ALTER TABLE messages ADD COLUMN image_path VARCHAR(500) NULL",
        "ALTER TABLE proxies ADD COLUMN group_ids VARCHAR(500) NULL",
        "ALTER TABLE proxies ADD COLUMN session_ids TEXT NULL",
        "ALTER TABLE proxies ADD COLUMN color VARCHAR(20) NOT NULL DEFAULT 'blue'",
        "CREATE INDEX ix_messages_telegram_message_id ON messages (telegram_message_id)",
        "CREATE INDEX ix_messages_session_chat_tg_msg ON messages (session_id, chat_id, telegram_message_id)",
        "ALTER TABLE customers ADD COLUMN access_hash VARCHAR(100) NULL",
        "ALTER TABLE tasks ADD COLUMN contact_card TEXT NULL",
        "ALTER TABLE session_groups ADD COLUMN owner_id INT NULL",
        "ALTER TABLE sessions ADD COLUMN owner_id INT NULL",
        "ALTER TABLE support_agents ADD COLUMN owner_id INT NULL",
        "ALTER TABLE customer_profiles ADD COLUMN owner_id INT NULL",
        "ALTER TABLE customers ADD COLUMN owner_id INT NULL",
        "ALTER TABLE materials ADD COLUMN owner_id INT NULL",
        "ALTER TABLE tasks ADD COLUMN owner_id INT NULL",
        "ALTER TABLE proxies ADD COLUMN owner_id INT NULL",
        "CREATE INDEX ix_session_groups_owner_id ON session_groups (owner_id)",
        "CREATE INDEX ix_sessions_owner_id ON sessions (owner_id)",
        "CREATE INDEX ix_support_agents_owner_id ON support_agents (owner_id)",
        "CREATE INDEX ix_customer_profiles_owner_id ON customer_profiles (owner_id)",
        "CREATE INDEX ix_customers_owner_id ON customers (owner_id)",
        "CREATE INDEX ix_materials_owner_id ON materials (owner_id)",
        "CREATE INDEX ix_tasks_owner_id ON tasks (owner_id)",
        "CREATE INDEX ix_proxies_owner_id ON proxies (owner_id)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except Exception:
                pass

    db = SessionLocal()
    try:
        _, test = ensure_default_users(db)
        for table in ["session_groups", "sessions", "support_agents", "customer_profiles", "customers", "materials", "tasks", "proxies"]:
            db.execute(text(f"UPDATE {table} SET owner_id = :owner_id WHERE owner_id IS NULL"), {"owner_id": test.id})
        db.commit()
    finally:
        db.close()
