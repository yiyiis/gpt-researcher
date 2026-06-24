"""
数据迁移：reports.json → SQLite (workspace.db)

启动时调用 migrate_if_needed(store)：
- 若 reports.json 存在且 SQLite 中无报告 → 创建默认工作区，导入全部历史报告。
- 幂等：已迁移过则跳过（靠 count_reports() > 0 判断）。
- 保留 reports.json 原文件作为备份，不删除。
"""
import json
import logging
from pathlib import Path
from typing import Optional

from .db import WorkspaceStore

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = "default"
DEFAULT_WORKSPACE_NAME = "默认工作区"


async def migrate_if_needed(
    store: WorkspaceStore, reports_json_path: Optional[Path] = None
) -> None:
    """若需要，把 reports.json 的数据迁移进 SQLite。幂等。"""
    await store.init_db()

    # 已有数据则跳过
    if await store.count_reports() > 0:
        logger.info("[migrate] SQLite 已有报告数据，跳过迁移")
        return

    if reports_json_path is None:
        reports_json_path = Path("data/reports.json")
    if not reports_json_path.exists():
        logger.info("[migrate] reports.json 不存在，创建默认工作区即可")
        await _ensure_default_workspace(store)
        return

    # 读取旧数据
    try:
        raw = reports_json_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning("[migrate] reports.json 格式异常（非 dict），跳过")
            await _ensure_default_workspace(store)
            return
    except Exception as e:
        logger.error(f"[migrate] 读取 reports.json 失败: {e}")
        await _ensure_default_workspace(store)
        return

    # 确保默认工作区存在
    await _ensure_default_workspace(store)

    migrated = 0
    for report_id, report in data.items():
        try:
            # 注入 workspace_id（旧数据无此字段，归到默认工作区）
            report["workspace_id"] = DEFAULT_WORKSPACE_ID
            await store.upsert_report(report_id, report)
            migrated += 1
        except Exception as e:
            logger.error(f"[migrate] 导入报告 {report_id} 失败: {e}")

    logger.info(
        f"[migrate] 迁移完成：{migrated}/{len(data)} 份报告导入「{DEFAULT_WORKSPACE_NAME}」。"
        f"原文件保留于 {reports_json_path}"
    )


async def _ensure_default_workspace(store: WorkspaceStore) -> None:
    """确保默认工作区存在（幂等）。"""
    existing = await store.get_workspace(DEFAULT_WORKSPACE_ID)
    if existing is None:
        await store.create_workspace(
            DEFAULT_WORKSPACE_ID, DEFAULT_WORKSPACE_NAME, "系统自动创建的默认工作区"
        )
        logger.info(f"[migrate] 已创建「{DEFAULT_WORKSPACE_NAME}」")
