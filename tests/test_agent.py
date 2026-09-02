"""Agent 模块测试（全 mock，不调用真实模型与网络）"""
from app.agent import _bing_search, _make_kb_tool, run_agent


def test_bing_search_parses_results(monkeypatch):
    """Bing 搜索：解析标题/链接/摘要"""
    html = """
    <html><body>
    <li class="b_algo">
      <h2><a href="https://example.com/1">结果标题一</a></h2>
      <div class="b_caption"><p>这是第一条搜索摘要内容</p></div>
    </li>
    <li class="b_algo">
      <h2><a href="https://example.com/2">结果标题二</a></h2>
      <p>这是第二条搜索摘要内容</p>
    </li>
    </body></html>
    """

    class FakeResp:
        text = html
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            pass

    monkeypatch.setattr("app.agent.requests.get", lambda *a, **k: FakeResp())
    results = _bing_search("测试关键词")
    assert len(results) == 2
    assert results[0]["title"] == "结果标题一"
    assert results[0]["href"] == "https://example.com/1"
    assert "第一条搜索摘要" in results[0]["body"]


def test_kb_tool_returns_formatted_results(monkeypatch):
    """知识库工具：把检索结果格式化为带来源的文本"""
    fake_results = [
        {
            "content": "RAG 流程：加载→切分→向量化→检索→生成",
            "source": "学习资料.md",
            "page": 0,
            "url": "",
            "score": 0.85,
        }
    ]
    monkeypatch.setattr("app.agent.similarity_search", lambda kb_id, query: fake_results)
    tool = _make_kb_tool(kb_id=1)
    output = tool.invoke({"query": "RAG 流程"})
    assert "学习资料.md" in output
    assert "85%" in output  # 相似度格式化
    assert "RAG 流程" in output


def test_kb_tool_empty_result(monkeypatch):
    """知识库无结果时应返回明确提示而非报错"""
    monkeypatch.setattr("app.agent.similarity_search", lambda kb_id, query: [])
    tool = _make_kb_tool(kb_id=1)
    output = tool.invoke({"query": "不存在的主题"})
    assert "没有找到" in output


def test_web_search_tool_degrades_on_failure(monkeypatch):
    """联网搜索失败时返回降级提示（工具失败不炸 Agent）"""

    def _boom(query):
        raise ConnectionError("网络不可达")

    monkeypatch.setattr("app.agent._bing_search", _boom)
    from app.agent import _web_search_tool

    tool = _web_search_tool()
    output = tool.invoke({"query": "测试"})
    assert "暂时不可用" in output


def test_run_agent_extracts_answer_and_trace():
    """run_agent：从消息序列提取最终回答与工具调用链"""
    from langchain_core.messages import AIMessage, ToolMessage

    class FakeAgent:
        def invoke(self, _input):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "search_knowledge_base", "args": {"query": "RAG"}, "id": "1"}],
                    ),
                    ToolMessage(content="[1] 来源: 文档.md | RAG 流程……", tool_call_id="1"),
                    AIMessage(content="根据知识库，RAG 流程是……"),
                ]
            }

    result = run_agent(FakeAgent(), "RAG 是什么？")
    assert "RAG 流程" in result["answer"]
    assert len(result["trace"]) == 2
    assert result["trace"][0]["step"] == "调用工具"
    assert result["trace"][1]["step"] == "工具返回"
