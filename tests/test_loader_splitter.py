"""切分与加载测试（全本地，无外部调用）"""
from pathlib import Path

from langchain_core.documents import Document

from app import loader, splitter


def test_recursive_split_pdf_text():
    """递归字符切分：长文本切成 ≤500 字符的片段，片段间有重叠"""
    long_text = "这是一段测试文本。" * 200  # 1800 字符
    doc = Document(page_content=long_text, metadata={"source": "test.pdf", "source_type": "pdf"})
    chunks = splitter.split_documents([doc])

    assert len(chunks) >= 4  # 1800 字符至少 4 片
    assert all(len(c.page_content) <= splitter.CHUNK_SIZE for c in chunks)
    # metadata 继承
    assert chunks[0].metadata["source"] == "test.pdf"
    # 相邻片段有重叠（50 字符），验证衔接内容不丢失
    assert chunks[0].page_content[-20:] in chunks[1].page_content


def test_markdown_structural_split():
    """Markdown 结构切分：按标题切成带层级 metadata 的片段"""
    md = "# 标题一\n\n正文一\n\n## 二级标题\n\n正文二\n\n# 标题二\n\n正文三"
    doc = Document(page_content=md, metadata={"source": "test.md", "source_type": "markdown"})
    chunks = splitter.split_documents([doc])

    assert len(chunks) == 3  # 两个一级标题块 + 一个二级标题块
    headers = {c.metadata.get("标题") for c in chunks}
    assert headers == {"标题一", "标题二"}
    assert all(c.metadata["source"] == "test.md" for c in chunks)


def test_auto_strategy_selection():
    """按类型自动选择：markdown 走结构切分，pdf 走递归切分"""
    md = "# A\n\n正文"
    md_doc = Document(page_content=md, metadata={"source_type": "markdown"})
    pdf_doc = Document(
        page_content="无标题的连续文本" * 100, metadata={"source_type": "pdf"}
    )
    chunks = splitter.split_documents([md_doc, pdf_doc])

    md_chunks = [c for c in chunks if c.metadata["source_type"] == "markdown"]
    pdf_chunks = [c for c in chunks if c.metadata["source_type"] == "pdf"]
    assert len(md_chunks) == 1  # 结构切分：一整块
    assert len(pdf_chunks) >= 2  # 递归切分：多块


def test_load_markdown(tmp_path):
    """Markdown 加载：读文件为 Document，metadata 记录来源"""
    f = tmp_path / "笔记.md"
    f.write_text("# 标题\n内容", encoding="utf-8")
    docs = loader.load_markdown(f)
    assert len(docs) == 1
    assert docs[0].metadata["source"] == "笔记.md"
    assert docs[0].metadata["source_type"] == "markdown"


def test_load_markdown_empty_rejected(tmp_path):
    """空 Markdown 应明确报错"""
    f = tmp_path / "空.md"
    f.write_text("   \n", encoding="utf-8")
    try:
        loader.load_markdown(f)
        assert False, "应抛出 ValueError"
    except ValueError:
        pass


def test_load_web_extracts_text(monkeypatch):
    """网页加载：丢弃脚本/导航等噪音，提取正文与标题"""
    long_text = "这是正文内容。" * 10  # 超过 MIN_WEB_TEXT_LENGTH 下限
    html = f"""
    <html><head><title>测试文章</title></head><body>
    <nav>导航菜单</nav>
    <script>var x = 1;</script>
    <p>{long_text}</p>
    </body></html>
    """

    class FakeResp:
        text = html
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(loader.requests, "get", lambda *a, **k: FakeResp())
    docs = loader.load_web("https://example.com/article")
    assert len(docs) == 1
    assert "导航菜单" not in docs[0].page_content  # 导航被丢弃
    assert "var x" not in docs[0].page_content     # 脚本被丢弃
    assert "这是正文内容" in docs[0].page_content
    assert docs[0].metadata["url"] == "https://example.com/article"


def test_load_web_insufficient_text_rejected(monkeypatch):
    """正文过短（可能登录墙/脚本渲染页）应明确报错"""
    class FakeResp:
        text = "<html><body>短内容</body></html>"
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(loader.requests, "get", lambda *a, **k: FakeResp())
    try:
        loader.load_web("https://example.com/login")
        assert False, "应抛出 ValueError"
    except ValueError:
        pass
