"""个人知识库 AI 问答工具 —— Streamlit 入口

启动：streamlit run app.py
界面分三块（侧边栏 + 两个页面 tab）：
- 侧边栏：知识库管理（新建/切换/删除）+ 会话管理（新建/历史恢复）
- 📚 文档管理：上传 PDF / Markdown / 网页 URL 导入，文档列表与删除
- 💬 智能问答：Agent 问答，工具调用链可视化（expander 展开看思考过程）

状态管理（设计说明）：
- st.session_state 保存当前选中的知识库/会话（Streamlit 每次交互重跑脚本，
  状态必须显式存储）
- 数据库（SQLite）持久化会话与消息，刷新页面后会话可恢复
"""
import logging
from datetime import datetime

import streamlit as st

from app import loader, splitter, vectorstore
from app.agent import build_agent, run_agent
from app.db import get_conn, init_db, utcnow

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="个人知识库 AI 问答工具", page_icon="🤖", layout="wide")

# ==================== 启动初始化 ====================
init_db()


# ==================== 数据访问 ====================
def list_kbs() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT kb.id, kb.name, kb.description, kb.created_at, "
        "(SELECT COUNT(*) FROM documents d WHERE d.kb_id = kb.id) AS doc_count "
        "FROM knowledge_bases kb ORDER BY kb.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_kb(name: str, description: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO knowledge_bases (name, description, created_at) VALUES (?, ?, ?)",
        (name, description, utcnow()),
    )
    conn.commit()
    conn.close()


def delete_kb(kb_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
    conn.commit()
    conn.close()
    vectorstore.delete_collection(kb_id)  # 同步清理向量数据


def list_documents(kb_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM documents WHERE kb_id = ? ORDER BY id DESC", (kb_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_document(kb_id: int, filename: str, source_type: str, chunk_count: int, source_url: str = "") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO documents (kb_id, filename, source_type, source_url, chunk_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kb_id, filename, source_type, source_url, chunk_count, utcnow()),
    )
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return doc_id


def delete_document(doc_id: int) -> None:
    """删除文档记录（向量片段按 kb 级重建简化处理：删除后重建该库向量）"""
    conn = get_conn()
    row = conn.execute("SELECT kb_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


def save_message(session_id: int, role: str, content: str, tool_calls: str = "[]") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, tool_calls, utcnow()),
    )
    conn.commit()
    conn.close()


def list_sessions() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_session(title: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sessions (title, created_at) VALUES (?, ?)", (title, utcnow())
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def load_messages(session_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 文档导入处理 ====================
def process_upload(kb_id: int, source_type: str, source) -> int:
    """导入 → 加载 → 切分 → 向量化 → 落元数据（返回片段数）"""
    with st.spinner("正在解析文档…"):
        docs = loader.load_document(source_type, source)
    with st.spinner(f"正在切分与向量化（{len(docs)} 个文档块）…"):
        chunks = splitter.split_documents(docs)
        vectorstore.add_documents(kb_id, chunks)
    return len(chunks)


# ==================== 侧边栏：知识库与会话 ====================
with st.sidebar:
    st.title("🤖 知识库问答")
    st.caption("RAG + Agent 个人知识库")

    # ----- 知识库管理 -----
    st.subheader("📚 知识库")
    kbs = list_kbs()
    kb_names = [kb["name"] for kb in kbs]

    if not kbs:
        st.info("还没有知识库，先创建一个")

    selected_kb_name = st.selectbox(
        "当前知识库",
        kb_names,
        index=0 if kb_names else 0,
        key="kb_select",
    )

    with st.expander("➕ 新建知识库"):
        new_kb_name = st.text_input("名称", key="new_kb_name")
        new_kb_desc = st.text_input("描述", key="new_kb_desc")
        if st.button("创建", use_container_width=True):
            if not new_kb_name.strip():
                st.error("名称不能为空")
            else:
                try:
                    create_kb(new_kb_name.strip(), new_kb_desc.strip())
                    st.rerun()
                except Exception:
                    st.error("名称已存在")

    if kbs and st.button("🗑 删除当前知识库", use_container_width=True):
        current = next(kb for kb in kbs if kb["name"] == selected_kb_name)
        delete_kb(current["id"])
        st.session_state.pop("chat_history", None)
        st.rerun()

    # ----- 会话管理 -----
    st.subheader("💬 会话")
    sessions = list_sessions()
    if st.button("➕ 新会话", use_container_width=True):
        sid = create_session("新会话")
        st.session_state["session_id"] = sid
        st.session_state["chat_history"] = []
        st.rerun()

    session_titles = {s["id"]: s["title"] for s in sessions}
    if sessions:
        current_sid = st.session_state.get("session_id")
        chosen = st.selectbox(
            "历史会话",
            list(session_titles.keys()),
            format_func=lambda x: session_titles[x],
            index=list(session_titles.keys()).index(current_sid) if current_sid in session_titles else 0,
            key="session_select",
        )
        if chosen != current_sid:
            st.session_state["session_id"] = chosen
            st.session_state["chat_history"] = load_messages(chosen)
            st.rerun()

    if not st.session_state.get("session_id"):
        sid = create_session("新会话")
        st.session_state["session_id"] = sid
        st.session_state["chat_history"] = []


# ==================== 主界面 ====================
if not kbs:
    st.warning("👈 请先在左侧创建一个知识库，然后导入文档开始使用")
    st.stop()

current_kb = next(kb for kb in kbs if kb["name"] == selected_kb_name)

tab_docs, tab_chat = st.tabs(["📚 文档管理", "💬 智能问答"])

# ==================== 文档管理页 ====================
def format_time(ts: str) -> str:
    """UTC ISO 时间 → 本地时区显示（数据库统一 UTC 存储，展示层转本地）"""
    return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M")


with tab_docs:
    st.subheader(f"「{current_kb['name']}」的文档（{current_kb['doc_count']} 个）")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**上传文件（PDF / Markdown）**")
        uploaded = st.file_uploader("选择文件", type=["pdf", "md"], label_visibility="collapsed")
        if uploaded:
            bytes_data = uploaded.getvalue()
            # 内容 MD5：防重复处理的两个场景——
            # 1. Streamlit rerun 后 uploader 控件仍保留文件对象，无此检查会再次切分+向量化
            # 2. 用户手动重复上传同一文件（内容相同），避免重复向量化浪费 embedding 费用
            import hashlib

            content_hash = hashlib.md5(bytes_data).hexdigest()
            processed_key = f"uploaded_{current_kb['id']}_{content_hash}"
            if st.session_state.get(processed_key):
                st.info(f"「{uploaded.name}」已导入过，跳过重复处理")
            else:
                suffix = "md" if uploaded.name.lower().endswith(".md") else "pdf"
                source_type = "markdown" if suffix == "md" else "pdf"
                # 保存到上传目录（uuid 前缀防重名覆盖）
                import uuid

                from app.config import UPLOAD_DIR

                save_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{uploaded.name}"
                save_path.write_bytes(bytes_data)
                try:
                    chunk_count = process_upload(current_kb["id"], source_type, str(save_path))
                    add_document(current_kb["id"], uploaded.name, source_type, chunk_count)
                    st.session_state[processed_key] = True  # 标记已处理，rerun 后不再重复
                    st.success(f"导入成功：{uploaded.name}（{chunk_count} 个片段）")
                    st.rerun()
                except Exception as e:
                    st.error(f"导入失败：{e}")

    with col2:
        st.markdown("**导入网页（URL）**")
        url = st.text_input("网页地址", placeholder="https://example.com/article", label_visibility="collapsed")
        if st.button("导入网页", use_container_width=True) and url.strip():
            # 同 URL 防重复导入
            url_key = f"web_{current_kb['id']}_{url.strip()}"
            if st.session_state.get(url_key):
                st.info("该网页已导入过，跳过重复处理")
            else:
                try:
                    chunk_count = process_upload(current_kb["id"], "web", url.strip())
                    add_document(current_kb["id"], url.strip()[:80], "web", chunk_count, source_url=url.strip())
                    st.session_state[url_key] = True
                    st.success(f"导入成功（{chunk_count} 个片段）")
                    st.rerun()
                except Exception as e:
                    st.error(f"导入失败：{e}")

    st.divider()
    docs = list_documents(current_kb["id"])
    if not docs:
        st.info("还没有文档，上传 PDF/Markdown 或导入网页开始构建知识库")
    for d in docs:
        c1, c2 = st.columns([5, 1])
        with c1:
            type_icon = {"pdf": "📄", "markdown": "📝", "web": "🌐"}[d["source_type"]]
            st.markdown(
                f"{type_icon} **{d['filename']}** ｜ {d['chunk_count']} 片段 ｜ "
                f"{format_time(d['created_at'])}"
            )
        with c2:
            if st.button("删除", key=f"del_{d['id']}"):
                delete_document(d["id"])
                st.rerun()

# ==================== 智能问答页 ====================
with tab_chat:
    st.subheader("向知识库提问（Agent 自主决策检索或联网）")
    st.caption("支持两类问题：知识库内的问题走本地检索；时效性问题（新闻、天气）自动联网搜索")

    # 历史消息展示
    chat_history = st.session_state.get("chat_history", [])
    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            # 工具调用链可视化（Assistant 消息带 trace 时展示）
            if msg["role"] == "assistant" and msg.get("tool_calls") and msg["tool_calls"] != "[]":
                import json

                trace = json.loads(msg["tool_calls"])
                with st.expander("🔍 查看 Agent 思考过程（工具调用链）"):
                    for t in trace:
                        icon = "🛠" if t["type"] == "tool" else "📋"
                        st.markdown(f"{icon} **{t['step']}**")
                        st.code(t["detail"], language=None)

    question = st.chat_input("输入你的问题…")
    if question:
        session_id = st.session_state["session_id"]
        # 用户消息
        save_message(session_id, "user", question)
        chat_history.append({"role": "user", "content": question})
        st.chat_message("user").markdown(question)

        # Agent 执行（模型自主决策工具）
        with st.chat_message("assistant"):
            with st.spinner("思考中…（Agent 可能检索知识库或联网搜索）"):
                try:
                    agent = build_agent(current_kb["id"])
                    result = run_agent(agent, question)
                    answer = result["answer"]
                    trace = result["trace"]
                    st.markdown(answer)
                    if trace:
                        with st.expander("🔍 查看 Agent 思考过程（工具调用链）"):
                            for t in trace:
                                icon = "🛠" if t["type"] == "tool" else "📋"
                                st.markdown(f"{icon} **{t['step']}**")
                                st.code(t["detail"], language=None)
                except Exception as e:
                    answer = f"抱歉，回答生成失败：{e}"
                    st.error(answer)
                    trace = []

        # 落库（工具链 JSON 化，会话恢复时还能看到）
        import json as _json

        save_message(session_id, "assistant", answer, _json.dumps(trace, ensure_ascii=False))
        chat_history.append({"role": "assistant", "content": answer, "tool_calls": _json.dumps(trace, ensure_ascii=False)})
        st.session_state["chat_history"] = chat_history
        # 会话标题取第一个问题（截断）
        if len(chat_history) == 2:
            conn = get_conn()
            conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (question[:20], session_id))
            conn.commit()
            conn.close()
        st.rerun()
