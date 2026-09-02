# 个人知识库 AI 问答工具 — 项目文档

## 项目概述

**项目名称**：个人知识库 AI 问答工具（personal-knowledge-qa-agent）
**项目类型**：本地 AI 工具（Streamlit 应用）
**目标用户**：个人用户（导入资料构建私人知识库并智能问答）
**用途**：实践项目（三个项目中最匹配 AI Agent 岗位）

---

## 技术栈

| 层面 | 技术 | 说明 |
|------|------|------|
| 界面 | Streamlit | 纯 Python 快速搭建交互界面 |
| Agent | LangChain 1.x create_agent | ReAct 循环 + 工具协议 |
| 大模型 | 阿里云百炼 qwen3.8-27b（函数调用） | OpenAI 兼容接口 |
| 向量化 | text-embedding-v3（自定义 Embeddings 类） | 百炼接口兼容适配（复用项目 1 方案） |
| 向量库 | Chroma（余弦空间，按知识库分 collection） | 嵌入式持久化 |
| 元数据 | SQLite | 知识库/文档/会话/消息 |
| 解析 | pypdf + BeautifulSoup | PDF 逐页提取 + 网页正文提取 |
| 测试 | pytest | 16 个用例（全 mock 外部服务） |

---

## ⭐ 协作规则（极其重要）

**本项目是用户的实践项目，用户是 AI 应用开发方向的开发者。**

1. **任何技术决策，由 Claude 列出多个方案**，解释优缺点与技术价值，让用户做选择。
2. **代码注释和文档用中文**，关键设计点要在注释中写明"为什么这样设计"。
3. **每完成一个功能/阶段，主动向用户解释**：做了什么、核心逻辑、技术评审可能会怎么问。
4. **遇到技术问题时，主动排查并提出解决方案**，修复后说明根因（踩坑过程值得记录）。
5. **保持代码分层清晰**：main.py（界面编排）/ app 包（config/db/embeddings/loader/splitter/vectorstore/agent），业务逻辑不放界面层。
6. **改动核心逻辑时，同步更新测试**，保证 `pytest` 全绿。

---

## 项目结构

```
project3/
├── main.py                  # Streamlit 入口（界面编排）
├── app/
│   ├── config.py            # 配置（.env 入口 + 数据目录）
│   ├── db.py                # SQLite 元数据
│   ├── embeddings.py        # 百炼自定义 Embeddings
│   ├── loader.py            # PDF/Markdown/网页加载
│   ├── splitter.py          # 双策略切分
│   ├── vectorstore.py       # Chroma 封装（余弦空间）
│   └── agent.py             # ReAct Agent + 两工具 + trace
├── tests/                   # pytest（16 用例，全 mock）
├── requirements.txt / .env.example / README.md / 技术问答要点.md
```

## 开发命令参考

| 命令 | 作用 | 执行目录 |
|------|------|---------|
| `.venv/Scripts/streamlit run main.py` | 启动应用（8501） | project3/ |
| `.venv/Scripts/python -m pytest tests/ -v` | 运行测试（约 3 秒） | project3/ |

- **提交门禁**：`git commit` 自动触发，跑 pytest + Python 语法编译检查
- **质量工程师 agent**：五维度代码质量审查
- **测试专员 agent**（tester1）：编写/运行 pytest 测试
- **/git-save**：双重门禁保存流程

## 踩坑记录

| 坑 | 根因与解决 |
|----|-----------|
| DuckDuckGo 搜索不可用 | 国内网络不可达（超时/TLS 失败）+ 包改名；换成 Bing 抓取 + 工具内降级 |
| 相似度出现负值 | Chroma 默认 l2 空间；collection 指定 hnsw:space=cosine |
| app.py 与 app/ 包导入冲突 | Streamlit 入口改名 main.py |
| 测试隔离失效 | db.py 导入时绑定 DB_PATH，monkeypatch 需同时 patch 使用方模块变量 |
