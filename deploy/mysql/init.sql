CREATE DATABASE IF NOT EXISTS tg_marketing
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'tg_user'@'%' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON tg_marketing.* TO 'tg_user'@'%';
FLUSH PRIVILEGES;

USE tg_marketing;

CREATE TABLE IF NOT EXISTS session_groups (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  description VARCHAR(255) NULL,
  color VARCHAR(20) NOT NULL DEFAULT 'blue',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_session_groups_name (name),
  INDEX ix_session_groups_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS support_agents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  remark TEXT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_support_agents_name (name),
  INDEX ix_support_agents_status (status),
  INDEX ix_support_agents_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL,
  avatar VARCHAR(500) NULL,
  phone VARCHAR(32) NOT NULL UNIQUE,
  session_name VARCHAR(150) NOT NULL UNIQUE,
  status ENUM('disconnected','connecting','connected','error') NOT NULL DEFAULT 'disconnected',
  last_login_at DATETIME NULL,
  last_health_check_at DATETIME NULL,
  health_status VARCHAR(50) NULL,
  error_message TEXT NULL,
  bidirectional_status VARCHAR(30) NOT NULL DEFAULT 'unchecked',
  bidirectional_detail TEXT NULL,
  last_bidirectional_check_at DATETIME NULL,
  group_id INT NULL,
  kf_id INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_sessions_username (username),
  INDEX ix_sessions_phone (phone),
  INDEX ix_sessions_status (status),
  INDEX ix_sessions_bidirectional_status (bidirectional_status),
  INDEX ix_sessions_group_id (group_id),
  INDEX ix_sessions_kf_id (kf_id),
  INDEX ix_sessions_status_group (status, group_id),
  INDEX ix_sessions_kf_status (kf_id, status),
  CONSTRAINT fk_sessions_group FOREIGN KEY (group_id) REFERENCES session_groups(id) ON DELETE SET NULL,
  CONSTRAINT fk_sessions_support_agent FOREIGN KEY (kf_id) REFERENCES support_agents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS session_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id INT NULL,
  action VARCHAR(50) NOT NULL,
  message TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  operator VARCHAR(100) NULL,
  INDEX ix_session_logs_session_id (session_id),
  INDEX ix_session_logs_action (action),
  INDEX ix_session_logs_created_at (created_at),
  INDEX ix_session_logs_session_created (session_id, created_at),
  CONSTRAINT fk_session_logs_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id INT NOT NULL,
  chat_id VARCHAR(100) NOT NULL,
  telegram_message_id INT NULL,
  sender VARCHAR(150) NULL,
  content TEXT NOT NULL,
  direction VARCHAR(20) NOT NULL DEFAULT 'inbound',
  read_status VARCHAR(20) NOT NULL DEFAULT 'unread',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_messages_session_created (session_id, created_at),
  INDEX ix_messages_chat_created (chat_id, created_at),
  INDEX ix_messages_telegram_message_id (telegram_message_id),
  INDEX ix_messages_session_chat_tg_msg (session_id, chat_id, telegram_message_id),
  CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  phone_number VARCHAR(32) NOT NULL,
  tg_id VARCHAR(100) NULL,
  access_hash VARCHAR(100) NULL,
  nickname VARCHAR(150) NULL,
  avatar VARCHAR(500) NULL,
  assigned_session_id INT NULL,
  kf_id INT NULL,
  send_status VARCHAR(30) NOT NULL DEFAULT 'pending',
  reply_status VARCHAR(30) NOT NULL DEFAULT 'not_replied',
  is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
  remark TEXT NULL,
  last_message_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_customers_phone_number (phone_number),
  INDEX ix_customers_tg_id (tg_id),
  INDEX ix_customers_assigned_session_id (assigned_session_id),
  INDEX ix_customers_kf_id (kf_id),
  INDEX ix_customers_send_status (send_status),
  INDEX ix_customers_reply_status (reply_status),
  INDEX ix_customers_is_favorite (is_favorite),
  INDEX ix_customers_last_message_at (last_message_at),
  INDEX ix_customers_created_at (created_at),
  INDEX ix_customers_phone_session (phone_number, assigned_session_id),
  CONSTRAINT fk_customers_session FOREIGN KEY (assigned_session_id) REFERENCES sessions(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS proxies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  scheme VARCHAR(20) NOT NULL DEFAULT 'http',
  host VARCHAR(255) NOT NULL,
  port INT NOT NULL,
  username VARCHAR(150) NULL,
  password VARCHAR(255) NULL,
  color VARCHAR(20) NOT NULL DEFAULT 'blue',
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  group_ids VARCHAR(500) NULL,
  session_ids TEXT NULL,
  status VARCHAR(50) NULL,
  error_message TEXT NULL,
  last_check_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_proxies_name (name),
  INDEX ix_proxies_scheme (scheme),
  INDEX ix_proxies_host (host),
  INDEX ix_proxies_is_active (is_active),
  INDEX ix_proxies_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS material_groups (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id INT NULL,
  name VARCHAR(150) NOT NULL,
  color VARCHAR(20) NOT NULL DEFAULT 'blue',
  remark TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_material_groups_owner_id (owner_id),
  INDEX ix_material_groups_name (name),
  INDEX ix_material_groups_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tasks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  content TEXT NOT NULL,
  image_path VARCHAR(500) NULL,
  contact_card TEXT NULL,
  send_type VARCHAR(20) NOT NULL DEFAULT 'single',
  material_group_id INT NULL,
  session_group_id INT NULL,
  targets_text TEXT NOT NULL,
  messages_per_target INT NOT NULL DEFAULT 3,
  status VARCHAR(50) NOT NULL DEFAULT 'draft',
  total_targets INT NOT NULL DEFAULT 0,
  sent_count INT NOT NULL DEFAULT 0,
  failed_count INT NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  last_run_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_tasks_name (name),
  INDEX ix_tasks_session_group_id (session_group_id),
  INDEX ix_tasks_send_type (send_type),
  INDEX ix_tasks_material_group_id (material_group_id),
  INDEX ix_tasks_status (status),
  INDEX ix_tasks_created_at (created_at),
  CONSTRAINT fk_tasks_session_group FOREIGN KEY (session_group_id) REFERENCES session_groups(id) ON DELETE SET NULL,
  CONSTRAINT fk_tasks_material_group FOREIGN KEY (material_group_id) REFERENCES material_groups(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS materials (
  id INT AUTO_INCREMENT PRIMARY KEY,
  group_id INT NULL,
  name VARCHAR(150) NOT NULL,
  material_type VARCHAR(20) NOT NULL,
  content TEXT NULL,
  file_path VARCHAR(500) NULL,
  priority INT NOT NULL DEFAULT 0,
  remark TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_materials_name (name),
  INDEX ix_materials_material_type (material_type),
  INDEX ix_materials_priority (priority),
  INDEX ix_materials_group_id (group_id),
  INDEX ix_materials_created_at (created_at),
  CONSTRAINT fk_materials_group FOREIGN KEY (group_id) REFERENCES material_groups(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS session_task_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id INT NULL,
  task_id INT NULL,
  task_name VARCHAR(150) NOT NULL,
  target_phone VARCHAR(32) NOT NULL,
  status VARCHAR(30) NOT NULL,
  message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_session_task_logs_session_id (session_id),
  INDEX ix_session_task_logs_task_id (task_id),
  INDEX ix_session_task_logs_task_name (task_name),
  INDEX ix_session_task_logs_target_phone (target_phone),
  INDEX ix_session_task_logs_status (status),
  INDEX ix_session_task_logs_created_at (created_at),
  INDEX ix_session_task_logs_session_created (session_id, created_at),
  INDEX ix_session_task_logs_session_status (session_id, status),
  CONSTRAINT fk_session_task_logs_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL,
  CONSTRAINT fk_session_task_logs_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
