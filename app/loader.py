"""文档加载：PDF / Markdown / 网页 → LangChain Document 列表

职责边界（设计说明）：loader 只负责"把各种来源读成纯文本 + 元数据"，
切分（chunking）是下一步的独立环节——加载与切分解耦，新增文档类型只改这里
"""
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from pypdf import PdfReader

# 网页抓取超时（秒）
FETCH_TIMEOUT = 15
# 网页正文最小长度（过滤掉没抓到内容的页面）
MIN_WEB_TEXT_LENGTH = 50

# 网页正文提取时丢弃的标签（导航/脚本/样式等噪音）
WEB_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}


def load_pdf(path: Path) -> list[Document]:
    """PDF：逐页提取文本，metadata 记录页码（引用展示"第 X 页"用）"""
    reader = PdfReader(str(path))
    docs = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            docs.append(
                Document(
                    page_content=text,
                    metadata={"source": path.name, "page": page_no, "source_type": "pdf"},
                )
            )
    if not docs:
        raise ValueError("PDF 无法提取文本（可能是扫描件，暂不支持 OCR）")
    return docs


def load_markdown(path: Path) -> list[Document]:
    """Markdown：整篇读入（结构切分在 splitter 环节按标题处理）"""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Markdown 文件内容为空")
    return [
        Document(
            page_content=text,
            metadata={"source": path.name, "page": 0, "source_type": "markdown"},
        )
    ]


def load_web(url: str) -> list[Document]:
    """网页：requests 抓取 + BeautifulSoup 提取正文

    安全说明：本工具面向个人本地使用，未限制内网地址（生产环境需加 SSRF 防护）
    """
    headers = {
        # 模拟浏览器 UA，部分站点会拒绝默认的 python-requests UA
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"  # 按页面声明/探测的编码解码，防乱码

    soup = BeautifulSoup(resp.text, "html.parser")
    # 标题：og:title 元信息优先，其次 <title>
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 丢弃导航/脚本等噪音标签后取正文
    for tag in soup(WEB_SKIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # 压缩连续空行（网页提取的文本常有大量空白）
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < MIN_WEB_TEXT_LENGTH:
        raise ValueError(f"未能提取到有效正文（可能页面需要登录或是纯脚本渲染）: {url}")

    return [
        Document(
            page_content=text,
            metadata={"source": title or url, "page": 0, "source_type": "web", "url": url},
        )
    ]


def load_document(source_type: str, source: str) -> list[Document]:
    """统一入口：按来源类型分发（source_type ∈ pdf / markdown / web）"""
    if source_type == "pdf":
        return load_pdf(Path(source))
    if source_type == "markdown":
        return load_markdown(Path(source))
    if source_type == "web":
        return load_web(source)
    raise ValueError(f"不支持的文档类型: {source_type}")
