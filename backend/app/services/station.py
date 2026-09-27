"""观测站点业务规则：状态流转、字段校验与筛选口径都收在这里。

状态只有四档：待入网、正常运行、降级运行、已停用。
流转规则（收尾态不能直接回到正常运行）：
  待入网   --办理入网--> 正常运行
  正常运行 --标记降级--> 降级运行
  正常运行/降级运行 --停用站点--> 已停用
降级、停用属于同口径的异常收尾态；想重新入网没有直达动作，避免误操作把站点带回正常运行。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "station"
REQUIRED_FIELDS = ["站点编码", "站点名称", "站点类别"]
PENDING_STATUS = "待入网"
ACTIVE_STATUS = "正常运行"
ABNORMAL_STATUSES = ["降级运行", "已停用"]
STATUS_ORDER = [PENDING_STATUS, ACTIVE_STATUS, *ABNORMAL_STATUSES]

# 动作 -> 目标状态
ACTION_RULES = {"办理入网": ACTIVE_STATUS, "标记降级": "降级运行", "停用站点": "已停用"}
# 动作 -> 允许从哪些当前状态执行；不在表里的一律拒绝
ACTION_SOURCES: dict[str, set[str]] = {
    "办理入网": {PENDING_STATUS},
    "标记降级": {ACTIVE_STATUS},
    "停用站点": {ACTIVE_STATUS, "降级运行"},
}
# 与看板、列表共用同一套统计口径
NEGATIVE_ACTIONS = ["标记降级", "停用站点"]


def _is_pending(status: str) -> bool:
    """待处理：尚未入网的站点；运行/降级/停用都不算待处理。"""
    return status == PENDING_STATUS


def _is_abnormal(status: str) -> bool:
    """异常量：降级运行与已停用按同一口径计入。"""
    return status in ABNORMAL_STATUSES


def _sync_flags(entry: dict[str, Any]) -> None:
    """pending/abnormal 永远从真实状态推导，避免历史数据把三处统计带歪。"""
    entry["pending"] = _is_pending(str(entry.get("status")))
    entry["abnormal"] = _is_abnormal(str(entry.get("status")))


class StationService:
    def __init__(self) -> None:
        # 状态流转 + 追加操作记录放在同一把锁里，重复点击不会留下半条状态
        self._lock = threading.RLock()
        # 站点 id -> 操作记录（仅追加成功动作，失败动作不入账）
        self._history: dict[int, list[dict[str, Any]]] = {}
        # 启动后先把存量数据的状态派生字段对齐
        with self._lock:
            for row in store.rows(MODULE):
                _sync_flags(row)

    # ------------------------------------------------------------------ 查询
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("站点编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, int]:
        """列表页三张统计卡与概览看板共用的口径，统一从状态推导。"""
        rows = store.rows(MODULE)
        online = sum(1 for row in rows if row.get("status") == ACTIVE_STATUS)
        degraded = sum(1 for row in rows if row.get("status") == "降级运行")
        disabled = sum(1 for row in rows if row.get("status") == "已停用")
        pending = sum(1 for row in rows if _is_pending(str(row.get("status"))))
        abnormal = degraded + disabled
        return {
            "online": online,
            "degraded": degraded,
            "disabled": disabled,
            "pending": pending,
            "abnormal": abnormal,
            "total": len(rows),
        }

    def history(self, entry_id: int) -> list[dict[str, Any]] | None:
        if self.get_entry(entry_id) is None:
            return None
        # 新记录在前，最近一次操作不会被挤掉
        return list(reversed(self._history.get(entry_id, [])))

    # ------------------------------------------------------------------ 写入
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        with self._lock:
            rows = store.rows(MODULE)
            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
            entry["status"] = PENDING_STATUS
            _sync_flags(entry)
            rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, *, operator: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """执行状态流转。任何校验失败都原样返回，不修改状态、不追加记录。"""
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测站点可执行范围"
        with self._lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"观测站点 {entry_id} 不存在或已归档"

            current = str(entry.get("status"))
            target = ACTION_RULES[action]

            if current == target:
                return None, f"站点当前已是「{current}」状态，无需重复{action}"
            allowed = ACTION_SOURCES[action]
            if current not in allowed:
                if current in ABNORMAL_STATUSES:
                    return (
                        None,
                        f"站点处于收尾状态「{current}」，不能直接{action}回到正常运行，"
                        "请先核实后重新登记入网",
                    )
                return None, f"站点当前为「{current}」，不允许执行{action}"

            # 校验全部通过后才落状态，失败不会留下半条状态
            entry["status"] = target
            _sync_flags(entry)
            self._history.setdefault(entry_id, []).append(
                {
                    "seq": len(self._history[entry_id]) + 1,
                    "action": action,
                    "from": current,
                    "to": target,
                    "operator": operator or "当前值班",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            return entry, f"观测站点已{action}（{current} → {target}）"
