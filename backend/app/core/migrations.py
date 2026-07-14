from sqlalchemy import text

from app.core.auth import ensure_default_users
from app.core.database import SessionLocal, engine


def run_lightweight_migrations() -> None:
    if engine.url.drivername.startswith("sqlite"):
        statements = [
            "ALTER TABLE materials ADD COLUMN group_id INTEGER NULL",
            "CREATE INDEX ix_materials_group_id ON materials (group_id)",
            "ALTER TABLE tasks ADD COLUMN send_type VARCHAR(20) NOT NULL DEFAULT 'single'",
            "ALTER TABLE tasks ADD COLUMN material_group_id INTEGER NULL",
            "CREATE INDEX ix_tasks_send_type ON tasks (send_type)",
            "CREATE INDEX ix_tasks_material_group_id ON tasks (material_group_id)",
            "ALTER TABLE customers ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT 0",
            "CREATE INDEX ix_customers_is_favorite ON customers (is_favorite)",
            "ALTER TABLE sessions ADD COLUMN bidirectional_status VARCHAR(30) NOT NULL DEFAULT 'unchecked'",
            "ALTER TABLE sessions ADD COLUMN bidirectional_detail TEXT NULL",
            "ALTER TABLE sessions ADD COLUMN last_bidirectional_check_at DATETIME NULL",
            "CREATE INDEX ix_sessions_bidirectional_status ON sessions (bidirectional_status)",
            "ALTER TABLE material_groups ADD COLUMN color VARCHAR(20) NOT NULL DEFAULT 'blue'",
            "ALTER TABLE customer_profiles ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'phone'",
            "CREATE INDEX ix_customer_profiles_target_type ON customer_profiles (target_type)",
            "ALTER TABLE tasks ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'phone'",
            "ALTER TABLE tasks ADD COLUMN target_source VARCHAR(20) NOT NULL DEFAULT 'imported'",
            "CREATE INDEX ix_tasks_target_source ON tasks (target_source)",
            "CREATE INDEX ix_tasks_target_type ON tasks (target_type)",
            "ALTER TABLE customers ADD COLUMN username VARCHAR(100) NULL",
            "CREATE INDEX ix_customers_username ON customers (username)",
            "ALTER TABLE tasks ADD COLUMN material_group_ids TEXT NULL",
            "ALTER TABLE task_targets ADD COLUMN payload_json TEXT NULL",
            "CREATE INDEX ix_session_task_logs_task_created ON session_task_logs (task_id, created_at)",
            "CREATE INDEX ix_session_task_logs_task_status_created ON session_task_logs (task_id, status, created_at)",
            "ALTER TABLE sessions ADD COLUMN contact_count INTEGER NULL",
            "ALTER TABLE sessions ADD COLUMN contacts_scanned_at DATETIME NULL",
        ]
        with engine.begin() as connection:
            for statement in statements:
                try:
                    connection.execute(text(statement))
                except Exception:
                    pass
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
        "ALTER TABLE materials ADD COLUMN group_id INT NULL",
        "CREATE INDEX ix_materials_group_id ON materials (group_id)",
        "ALTER TABLE materials ADD CONSTRAINT fk_materials_group FOREIGN KEY (group_id) REFERENCES material_groups(id) ON DELETE SET NULL",
        "ALTER TABLE tasks ADD COLUMN send_type VARCHAR(20) NOT NULL DEFAULT 'single'",
        "ALTER TABLE tasks ADD COLUMN material_group_id INT NULL",
        "CREATE INDEX ix_tasks_send_type ON tasks (send_type)",
        "CREATE INDEX ix_tasks_material_group_id ON tasks (material_group_id)",
        "ALTER TABLE tasks ADD CONSTRAINT fk_tasks_material_group FOREIGN KEY (material_group_id) REFERENCES material_groups(id) ON DELETE SET NULL",
        "ALTER TABLE customers ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX ix_customers_is_favorite ON customers (is_favorite)",
        "ALTER TABLE sessions ADD COLUMN bidirectional_status VARCHAR(30) NOT NULL DEFAULT 'unchecked'",
        "ALTER TABLE sessions ADD COLUMN bidirectional_detail TEXT NULL",
        "ALTER TABLE sessions ADD COLUMN last_bidirectional_check_at DATETIME NULL",
        "CREATE INDEX ix_sessions_bidirectional_status ON sessions (bidirectional_status)",
        "ALTER TABLE material_groups ADD COLUMN color VARCHAR(20) NOT NULL DEFAULT 'blue'",
        "ALTER TABLE customer_profiles ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'phone'",
        "CREATE INDEX ix_customer_profiles_target_type ON customer_profiles (target_type)",
        "ALTER TABLE tasks ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'phone'",
        "ALTER TABLE tasks ADD COLUMN target_source VARCHAR(20) NOT NULL DEFAULT 'imported'",
        "CREATE INDEX ix_tasks_target_source ON tasks (target_source)",
        "CREATE INDEX ix_tasks_target_type ON tasks (target_type)",
        "ALTER TABLE customers ADD COLUMN username VARCHAR(100) NULL",
        "CREATE INDEX ix_customers_username ON customers (username)",
        "ALTER TABLE customers MODIFY COLUMN phone_number VARCHAR(32) NULL",
        "ALTER TABLE session_task_logs MODIFY COLUMN target_phone VARCHAR(100) NOT NULL",
        "ALTER TABLE tasks ADD COLUMN material_group_ids TEXT NULL",
        "ALTER TABLE task_targets ADD COLUMN payload_json TEXT NULL",
        "CREATE INDEX ix_session_task_logs_task_created ON session_task_logs (task_id, created_at)",
        "CREATE INDEX ix_session_task_logs_task_status_created ON session_task_logs (task_id, status, created_at)",
        "ALTER TABLE sessions ADD COLUMN contact_count INT NULL",
        "ALTER TABLE sessions ADD COLUMN contacts_scanned_at DATETIME NULL",
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
        for table in ["session_groups", "sessions", "support_agents", "customer_profiles", "customers", "material_groups", "materials", "tasks", "proxies"]:
            db.execute(text(f"UPDATE {table} SET owner_id = :owner_id WHERE owner_id IS NULL"), {"owner_id": test.id})
        db.commit()
    finally:
        db.close()
