"""Chroma 向量库封装：按知识库分 collection 隔离

复用项目 1 客服系统的踩坑经验（设计说明）：
- langchain-chroma 的 relevance_score_fn 配置不生效，返回的是距离而非相似度
  （实测：同义文本距离 0.07，直观上应该是 0.93 的相似度）
- 本封装手动做距离→相似度转换（1 - distance），分数语义直观、展示可靠
"""
import chromadb
from langchain_chroma import Chroma

from app.config import CHROMA_DIR
from app.embeddings import BailianEmbeddings

# 检索片段数（top-k）
TOP_K = 4

# 持久化客户端（进程内复用，避免每次请求重建连接）
_persistent_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

_embeddings = BailianEmbeddings()


def _collection_name(kb_id: int) -> str:
    """每个知识库一个独立 collection：向量隔离，删除知识库只清自己的集合"""
    return f"kb_{kb_id}"


def get_store(kb_id: int) -> Chroma:
    """获取指定知识库的向量库实例（collection 不存在时自动创建）

    hnsw:space 指定余弦空间（Chroma 默认 l2 距离，1-l2 会产生负"相似度"，
    余弦空间下 1-distance 即余弦相似度，分数语义直观——项目 1 的踩坑经验）
    """
    return Chroma(
        client=_persistent_client,
        collection_name=_collection_name(kb_id),
        embedding_function=_embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )


def add_documents(kb_id: int, chunks: list) -> int:
    """向量化并写入片段（返回写入数量）"""
    store = get_store(kb_id)
    store.add_documents(chunks)
    return len(chunks)


def similarity_search(kb_id: int, query: str, top_k: int = TOP_K) -> list[dict]:
    """相似度检索：返回 [{content, source, page, url, score}]（相似度 0~1，高=相关）

    为什么手动转换分数（项目 1 踩坑）：
    langchain-chroma 的 similarity_search_with_score 返回余弦距离，
    与直觉的"相似度"相反且难解释——统一转成相似度后，
    界面上"85% 相关"这种展示对用户才是可理解的
    """
    store = get_store(kb_id)
    results = store.similarity_search_with_score(query, k=top_k)
    return [
        {
            "content": doc.page_content,
            "source": doc.metadata.get("source", ""),
            "page": doc.metadata.get("page", 0),
            "url": doc.metadata.get("url", ""),
            "score": round(1 - distance, 4),  # 余弦距离 → 相似度
        }
        for doc, distance in results
    ]


def delete_collection(kb_id: int) -> None:
    """删除知识库对应的向量 collection（失败不抛出——数据清理尽力而为）"""
    try:
        _persistent_client.delete_collection(_collection_name(kb_id))
    except Exception:
        pass  # collection 可能本就不存在
