"""pytest 公共 fixture

测试原则（与项目 1/2 一致）：
- 不调用真实外部服务（百炼 API / 网络）——快速、稳定、零费用
- 用临时数据目录，测试数据自清理，互不影响
"""
import sys
from pathlib import Path

import pytest

# 项目根目录加入 sys.path（保证 app 包可导入）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def tmp_data_dir(tmp_path, monkeypatch):
    """临时数据目录：替换 config 与各模块中已导入绑定的路径变量

    注意：db.py 顶部 `from app.config import DB_PATH` 是导入时绑定，
    只 monkeypatch config 不生效，必须同时 patch 使用方的模块变量
    """
    import app.config as config
    import app.db as db

    data_dir = tmp_path / "data"
    db_path = data_dir / "app.db"
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "CHROMA_DIR", data_dir / "chroma")
    monkeypatch.setattr(config, "UPLOAD_DIR", data_dir / "uploads")
    monkeypatch.setattr(db, "DB_PATH", db_path)  # 关键：修使用方模块的绑定
    data_dir.mkdir(exist_ok=True)
    return data_dir
