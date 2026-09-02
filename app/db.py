"""SQLite 元数据库：知识库 / 文档 / 会话 / 消息

设计说明（面试可讲）：
- 为什么向量单独放 Chroma 而元数据放 SQLite：
  向量检索与业务查询是两种访问模式（语义相似度 vs 结构化过滤），
  各自用最适合的存储；SQLite 存"有哪些文档、状态如何"，Chroma 存"片段向量"
- 时间统一 UTC 存储（项目 1/2 的经验），展示层转本地时区
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,             -- 展示名（网页为标题）
    source_type TEXT NOT NULL,          -- pdf / markdown / web
    source_url TEXT NOT NULL DEFAULT '',-- 网页导入时的原始 URL
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '新会话',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                 -- user / assistant
    content TEXT NOT NULL,
    tool_calls TEXT NOT NULL DEFAULT '[]',  -- JSON：Agent 工具调用链（可视化用）
    created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    """UTC 时间字符串（ISO 8601）"""
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    """获取连接（每次新建，SQLite 单写者模型 + Streamlit 重跑频繁，短连接最稳）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # 级联删除生效
    return conn


def init_db(db_path: Path | None = None) -> None:
    """初始化表结构（幂等，应用启动时调用）"""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
