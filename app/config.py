"""配置模块：环境变量统一入口

数据目录约定（与项目 1/2 一致）：
- 所有数据放项目目录 data/ 下（SQLite 数据库、Chroma 向量库、上传文件）
- 绝不用用户目录/系统盘默认路径，保证可整体备份与迁移
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/config.py 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 数据目录（SQLite / Chroma / 上传文件都在这里）
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# SQLite 元数据库：知识库/文档/会话记录（单用户本地工具，SQLite 零运维——面试讲选型）
DB_PATH = DATA_DIR / "app.db"

# Chroma 向量库持久化目录（按知识库分 collection）
CHROMA_DIR = DATA_DIR / "chroma"
CHROMA_DIR.mkdir(exist_ok=True)

# 上传文件目录
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ===== 大模型配置 =====
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.8-27b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# 百炼 OpenAI 兼容接口
BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
