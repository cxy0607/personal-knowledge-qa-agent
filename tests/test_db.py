"""SQLite 元数据库测试"""
from app.db import get_conn, init_db, utcnow


def test_init_db_creates_tables(tmp_data_dir):
    """初始化后应有 4 张表，且幂等（重复执行不报错）"""
    init_db()
    init_db()  # 幂等验证
    conn = get_conn()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    assert {"knowledge_bases", "documents", "sessions", "messages"} <= tables


def test_crud_knowledge_base(tmp_data_dir):
    """知识库增删 + 文档级联删除"""
    init_db()
    conn = get_conn()
    conn.execute(
        "INSERT INTO knowledge_bases (name, description, created_at) VALUES (?, ?, ?)",
        ("测试库", "描述", utcnow()),
    )
    conn.commit()
    kb_id = conn.execute("SELECT id FROM knowledge_bases WHERE name='测试库'").fetchone()["id"]

    conn.execute(
        "INSERT INTO documents (kb_id, filename, source_type, created_at) VALUES (?, ?, ?, ?)",
        (kb_id, "a.pdf", "pdf", utcnow()),
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"] == 1

    # 删除知识库 → 文档级联删除（PRAGMA foreign_keys 生效）
    conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"] == 0
    conn.close()


def test_session_message_roundtrip(tmp_data_dir):
    """会话与消息保存/读取（会话恢复的数据基础）"""
    init_db()
    conn = get_conn()
    conn.execute("INSERT INTO sessions (title, created_at) VALUES (?, ?)", ("会话A", utcnow()))
    conn.commit()
    sid = conn.execute("SELECT id FROM sessions WHERE title='会话A'").fetchone()["id"]

    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
        (sid, "user", "问题", "[]", utcnow()),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (sid,)
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "问题"


def test_utcnow_format():
    """时间格式为带时区的 ISO 8601（UTC 约定）"""
    ts = utcnow()
    assert ts.endswith("+00:00") or "Z" in ts  # datetime.isoformat 带偏移
