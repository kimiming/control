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
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_session_groups_name (name),
  INDEX ix_session_groups_created_at (created_at)
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
  group_id INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_sessions_username (username),
  INDEX ix_sessions_phone (phone),
  INDEX ix_sessions_status (status),
  INDEX ix_sessions_group_id (group_id),
  INDEX ix_sessions_status_group (status, group_id),
  CONSTRAINT fk_sessions_group FOREIGN KEY (group_id) REFERENCES session_groups(id) ON DELETE SET NULL
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
  sender VARCHAR(150) NULL,
  content TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_messages_session_created (session_id, created_at),
  INDEX ix_messages_chat_created (chat_id, created_at),
  CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
