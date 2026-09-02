"""ReAct Agent：模型自主决策「用知识库检索还是联网搜索」（项目核心亮点）

架构（面试必讲）：
- LangChain 1.x 的 create_agent 构建 ReAct 循环：思考(Thought) → 行动(Action: 调工具) → 观察(Observation) → 继续思考，直到能给出最终答案
- 两个工具：
  1. search_knowledge_base —— 检索当前知识库（本地向量相似度检索，带来源引用）
  2. web_search —— DuckDuckGo 联网搜索（知识库没有的信息）
- 模型自主决策：问知识库内的问题 → 只用检索；问"今天天气" → 自动联网；
  知识库内容过时 → 两个工具都用，交叉验证
- 工具调用链全程记录（agent_trace），Streamlit 界面可视化展示思考过程

RAG vs Agent（面试高频对比）：
- RAG 是固定流水线（检索→拼上下文→生成），路径确定、可控、成本低
- Agent 是模型自主决策（选哪个工具、用几次、结果怎么用），灵活但成本高、可能失控
- 什么时候用 Agent：任务需要多步推理/多工具协作时；简单问答用 RAG 更划算
"""
import logging

import requests
from bs4 import BeautifulSoup
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.config import BAILIAN_BASE_URL, DASHSCOPE_API_KEY, LLM_MODEL
from app.vectorstore import similarity_search

logger = logging.getLogger("app")

# 联网搜索返回结果条数
WEB_SEARCH_RESULTS = 3
# 搜索请求超时（秒）
SEARCH_TIMEOUT = 15

# 搜索引擎：Bing（国内可达；DuckDuckGo 被墙——面试可讲这个选型调整过程）
BING_SEARCH_URL = "https://cn.bing.com/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _chat_model() -> ChatOpenAI:
    """对话模型（指向百炼兼容接口；qwen3.8-27b 支持函数调用）"""
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=DASHSCOPE_API_KEY,
        base_url=BAILIAN_BASE_URL,
        temperature=0.3,  # Agent 决策要稳定，低温度（与写作类 0.7 形成对比——按任务调温）
    )


def _make_kb_tool(kb_id: int):
    """知识库检索工具（闭包捕获当前选中的知识库 id）

    为什么工具要动态创建（面试可讲）：
    用户在界面切换知识库后，工具的目标随之改变——用工厂函数每次生成
    绑定当前 kb_id 的工具实例，简单可靠
    """

    @tool
    def search_knowledge_base(query: str) -> str:
        """在个人知识库中检索相关内容。当用户的问题可能涉及已导入的文档时使用此工具。

        Args:
            query: 检索关键词或问题
        """
        results = similarity_search(kb_id, query)
        if not results:
            return "知识库中没有找到相关内容。"
        lines = []
        for i, r in enumerate(results, 1):
            src = r["source"]
            page_info = f"（第{r['page']}页）" if r["page"] else ""
            lines.append(f"[{i}] 来源: {src}{page_info} | 相关度: {r['score']:.0%}\n{r['content']}")
        return "\n\n".join(lines)

    return search_knowledge_base


def _bing_search(query: str) -> list[dict]:
    """Bing 搜索抓取：requests + BeautifulSoup 解析结果页

    为什么不用 DuckDuckGo 的现成库（面试可讲）：
    初版用 duckduckgo-search，但国内网络不可达（超时/TLS 失败），
    换成 cn.bing.com 抓取——与项目网页导入同一套技术栈，零额外依赖
    """
    resp = requests.get(
        BING_SEARCH_URL,
        params={"q": query},
        headers={"User-Agent": UA},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for li in soup.select("li.b_algo")[:WEB_SEARCH_RESULTS]:
        a = li.select_one("h2 a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        cap = li.select_one("div.b_caption p, p")
        body = cap.get_text(strip=True)[:200] if cap else ""
        results.append({"title": title, "href": href, "body": body})
    return results


def _web_search_tool():
    """联网搜索工具（Bing 抓取：免费、无需 API key）"""

    @tool
    def web_search(query: str) -> str:
        """联网搜索最新信息。当知识库检索不到答案、或问题涉及时效性信息（新闻、天气等）时使用。

        Args:
            query: 搜索关键词
        """
        try:
            results = _bing_search(query)
        except Exception as e:
            # 工具失败不炸整个 Agent：返回错误文本让模型降级回答
            logger.warning("联网搜索失败: %s", e)
            return f"联网搜索暂时不可用（{e}）。请基于已有知识回答，或告知用户稍后再试。"
        if not results:
            return "没有搜到相关内容。"
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r['title']}\n{r['href']}\n{r['body']}")
        return "\n\n".join(lines)

    return web_search


SYSTEM_PROMPT = """你是一个个人知识库问答助手，名字叫「小知」。

工作方式：
1. 当用户的问题可能涉及已导入的文档内容时，先用 search_knowledge_base 检索知识库
2. 当知识库没有相关内容、或问题需要最新/实时信息时，用 web_search 联网搜索
3. 综合检索结果回答问题；回答时注明信息来源（文件或网页）

回答要求：
- 用中文回答；基于检索到的内容作答，不编造
- 如果所有工具都没有找到相关信息，如实告诉用户"没有找到相关资料"
"""


def build_agent(kb_id: int):
    """构建 Agent（每次问答创建：工具绑定了当前知识库，代价可忽略）"""
    model = _chat_model()
    tools = [_make_kb_tool(kb_id), _web_search_tool()]
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT)


def run_agent(agent, question: str) -> dict:
    """执行 Agent，返回 {answer, trace}；trace 为工具调用链（界面可视化用）

    容错：Agent 执行失败（模型超时等）抛出异常，由界面层捕获展示友好提示
    """
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    messages = result["messages"]
    answer = ""
    trace = []  # [{step, type, detail}] 思考过程记录
    for msg in messages:
        if msg.type == "ai":
            # 工具调用记录（ReAct 的 Action 步骤）
            for call in getattr(msg, "tool_calls", []) or []:
                trace.append(
                    {
                        "step": "调用工具",
                        "type": "tool",
                        "detail": f"{call['name']}({call.get('args', {})})",
                    }
                )
            # 最终回答
            if msg.content:
                answer = msg.content
        elif msg.type == "tool":
            # 工具返回（Observation）
            trace.append(
                {
                    "step": "工具返回",
                    "type": "observation",
                    "detail": (msg.content or "")[:200],  # 界面截断展示
                }
            )
    return {"answer": answer or "（模型未给出回答，请重试）", "trace": trace}
