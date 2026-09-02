"""文本切分：两种策略按文档类型自动选择（本项目特色，两种策略对比）

策略一：递归字符切分（RecursiveCharacterTextSplitter）
- 适用：PDF、网页（无标题结构的连续文本）
- 原理：按 \n\n → \n → 。 等分隔符优先级递归切分，尽量保证片段落在语义边界
- 参数：500 字符 / 50 重叠（重叠避免关键句被切断，保证上下文连续）

策略二：Markdown 结构切分（MarkdownHeaderTextSplitter）
- 适用：Markdown（有 # / ## / ### 标题层级）
- 原理：按标题把文档切成"标题 + 正文"的结构化片段，每个片段自带章节上下文
- 好处：片段粒度对齐文章结构，检索质量高于机械定长切分

为什么两种策略并存（设计说明）：
定长切分"一刀切"，遇到有结构的 Markdown 会把章节标题和正文拆开、丢失层级信息；
结构切分对无标题的 PDF 则退化为整篇一大块。按文档类型自动选择 = 各取所长
"""
from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

# 递归字符切分参数
CHUNK_SIZE = 500      # 片段最大字符数
CHUNK_OVERLAP = 50    # 相邻片段重叠字符数

# Markdown 标题层级（切分边界）
MD_HEADERS = [
    ("#", "标题"),
    ("##", "二级标题"),
    ("###", "三级标题"),
]

_recursive_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
)
_md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=MD_HEADERS)


def _is_markdown(doc: Document) -> bool:
    """判断文档是否适合结构切分（来源类型是 markdown 或内容含大量标题语法）"""
    if doc.metadata.get("source_type") == "markdown":
        return True
    # 网页正文也可能含 markdown 标题，检测文本前部是否出现标题行
    return any(line.strip().startswith("#") for line in doc.page_content.splitlines()[:50])


def split_documents(docs: list[Document]) -> list[Document]:
    """按文档类型自动选择切分策略，返回片段列表（metadata 继承来源信息）"""
    chunks: list[Document] = []
    for doc in docs:
        if _is_markdown(doc):
            # 结构切分后补上元数据（MarkdownHeaderTextSplitter 只保留标题层级到 metadata）
            for md_chunk in _md_splitter.split_text(doc.page_content):
                md_chunk.metadata.update(doc.metadata)
                chunks.append(md_chunk)
        else:
            chunks.extend(_recursive_splitter.split_documents([doc]))
    return chunks
