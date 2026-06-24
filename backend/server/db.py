"""
SQLite 存储层 — 工作区（Workspace）持久化。

用 Python 标准库 sqlite3（零依赖），单文件数据库 data/workspace.db。
所有方法都是 async（用 asyncio.to_thread 包同步 sqlite3 调用）。

为后续 agent 记忆、skill 配置预留扩展性：
- workspaces: 工作区
- reports: 研究报告（归属工作区）
- documents: 上传的文档/资料（归属工作区）
- artifacts: 产出文件（PDF/Word 等，归属工作区）
"""
import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


class WorkspaceStore:
    """工作区 + 报告 + 文档 + 产出文件的 SQLite 存储。"""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        """每次操作新建连接（sqlite3 连接轻量，且线程安全）。开启 WAL + 外键。"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def init_db(self) -> None:
        """建表（幂等）。应用启动时调用一次。"""
        async with self._init_lock:
            if self._initialized:
                return

            def _do_init():
                conn = self._connect()
                try:
                    cur = conn.cursor()
                    cur.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS workspaces (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            description TEXT,
                            created_at INTEGER,
                            updated_at INTEGER
                        );

                        CREATE TABLE IF NOT EXISTS reports (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            question TEXT,
                            answer TEXT,
                            ordered_data TEXT,
                            chat_messages TEXT,
                            timestamp INTEGER,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
                                ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_reports_workspace
                            ON reports(workspace_id);

                        CREATE TABLE IF NOT EXISTS documents (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            filename TEXT,
                            file_path TEXT,
                            file_size INTEGER,
                            uploaded_at INTEGER,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
                                ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_documents_workspace
                            ON documents(workspace_id);

                        CREATE TABLE IF NOT EXISTS artifacts (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            report_id TEXT,
                            filename TEXT,
                            file_path TEXT,
                            artifact_type TEXT,
                            created_at INTEGER,
                            FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
                                ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_artifacts_workspace
                            ON artifacts(workspace_id);
                        """
                    )
                    conn.commit()
                finally:
                    conn.close()

            await asyncio.to_thread(_do_init)
            self._initialized = True

    # ======================== 工作区 CRUD ========================

    async def list_workspaces(self) -> List[Dict[str, Any]]:
        def _do():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM workspaces ORDER BY created_at ASC"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def get_workspace(self, ws_id: str) -> Optional[Dict[str, Any]]:
        def _do():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM workspaces WHERE id = ?", (ws_id,)
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def create_workspace(
        self, ws_id: str, name: str, description: str = ""
    ) -> Dict[str, Any]:
        now = _now_ms()

        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO workspaces (id, name, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ws_id, name, description, now, now),
                )
                conn.commit()
                return {
                    "id": ws_id,
                    "name": name,
                    "description": description,
                    "created_at": now,
                    "updated_at": now,
                }
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def update_workspace(
        self, ws_id: str, name: Optional[str] = None, description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        existing = await self.get_workspace(ws_id)
        if existing is None:
            return None
        new_name = name if name is not None else existing["name"]
        new_desc = description if description is not None else existing.get("description", "")
        now = _now_ms()

        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE workspaces SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                    (new_name, new_desc, now, ws_id),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_do)
        return await self.get_workspace(ws_id)

    async def delete_workspace(self, ws_id: str) -> bool:
        def _do():
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM workspaces WHERE id = ?", (ws_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    # ======================== 报告 CRUD ========================

    async def list_reports(
        self, workspace_id: Optional[str] = None, report_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """列出报告。可按 workspace_id 过滤，或按 report_ids 过滤。"""

        def _do():
            conn = self._connect()
            try:
                if report_ids is not None:
                    if not report_ids:
                        return []
                    placeholders = ",".join("?" * len(report_ids))
                    if workspace_id:
                        rows = conn.execute(
                            f"SELECT * FROM reports WHERE workspace_id = ? AND id IN ({placeholders}) "
                            "ORDER BY timestamp DESC",
                            [workspace_id] + report_ids,
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT * FROM reports WHERE id IN ({placeholders}) ORDER BY timestamp DESC",
                            report_ids,
                        ).fetchall()
                elif workspace_id:
                    rows = conn.execute(
                        "SELECT * FROM reports WHERE workspace_id = ? ORDER BY timestamp DESC",
                        (workspace_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM reports ORDER BY timestamp DESC"
                    ).fetchall()
                return [self._row_to_report(r) for r in rows]
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        def _do():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM reports WHERE id = ?", (report_id,)
                ).fetchone()
                return self._row_to_report(row) if row else None
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def upsert_report(self, report_id: str, report: Dict[str, Any]) -> None:
        """插入或更新报告。report 需含 workspace_id。"""
        ws_id = report.get("workspace_id") or report.get("workspaceId")
        if not ws_id:
            raise ValueError("报告缺少 workspace_id")

        ordered_data = report.get("orderedData") or report.get("ordered_data") or []
        chat_messages = report.get("chatMessages") or report.get("chat_messages") or []
        timestamp = report.get("timestamp")
        if not isinstance(timestamp, int):
            timestamp = _now_ms()

        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO reports (id, workspace_id, question, answer, ordered_data, "
                    "chat_messages, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "workspace_id=excluded.workspace_id, question=excluded.question, "
                    "answer=excluded.answer, ordered_data=excluded.ordered_data, "
                    "chat_messages=excluded.chat_messages, timestamp=excluded.timestamp",
                    (
                        report_id,
                        ws_id,
                        report.get("question", ""),
                        report.get("answer", ""),
                        json.dumps(ordered_data, ensure_ascii=False),
                        json.dumps(chat_messages, ensure_ascii=False),
                        timestamp,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_do)

    async def delete_report(self, report_id: str) -> bool:
        def _do():
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    @staticmethod
    def _row_to_report(row: sqlite3.Row) -> Dict[str, Any]:
        """把数据库行转成前端期望的报告格式（保持 orderedData/chatMessages 为数组）。"""
        d = dict(row)
        try:
            d["orderedData"] = json.loads(d.pop("ordered_data") or "[]")
        except (json.JSONDecodeError, KeyError):
            d["orderedData"] = []
            d.pop("ordered_data", None)
        try:
            d["chatMessages"] = json.loads(d.pop("chat_messages") or "[]")
        except (json.JSONDecodeError, KeyError):
            d["chatMessages"] = []
            d.pop("chat_messages", None)
        d["workspaceId"] = d.pop("workspace_id")
        return d

    # ======================== 文档 CRUD ========================

    async def list_documents(self, workspace_id: str) -> List[Dict[str, Any]]:
        def _do():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE workspace_id = ? ORDER BY uploaded_at DESC",
                    (workspace_id,),
                ).fetchall()
                result = []
                for r in rows:
                    item = dict(r)
                    item["workspaceId"] = item.pop("workspace_id")
                    item["filePath"] = item.pop("file_path")
                    item["fileSize"] = item.pop("file_size")
                    item["uploadedAt"] = item.pop("uploaded_at")
                    result.append(item)
                return result
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def add_document(
        self, doc_id: str, workspace_id: str, filename: str, file_path: str, file_size: int
    ) -> Dict[str, Any]:
        now = _now_ms()

        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO documents (id, workspace_id, filename, file_path, file_size, "
                    "uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (doc_id, workspace_id, filename, file_path, file_size, now),
                )
                conn.commit()
                return {
                    "id": doc_id,
                    "workspaceId": workspace_id,
                    "filename": filename,
                    "filePath": file_path,
                    "fileSize": file_size,
                    "uploadedAt": now,
                }
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    async def delete_document(self, doc_id: str) -> Optional[str]:
        """删除文档记录，返回 file_path（供调用方删实际文件）。"""
        def _do():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT file_path FROM documents WHERE id = ?", (doc_id,)
                ).fetchone()
                if row is None:
                    return None
                conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                conn.commit()
                return row["file_path"]
            finally:
                conn.close()

        return await asyncio.to_thread(_do)

    # ======================== 统计 ========================

    async def count_reports(self) -> int:
        def _do():
            conn = self._connect()
            try:
                return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            finally:
                conn.close()

        return await asyncio.to_thread(_do)
