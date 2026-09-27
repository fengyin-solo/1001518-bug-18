"""观测站点业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "station"
REQUIRED_FIELDS = ["站点编码", "站点名称", "站点类别"]
STATUS_ORDER = ["待入网", "正常运行", "降级运行", "已停用"]
ACTION_RULES = {"办理入网": "正常运行", "标记降级": "降级运行", "停用站点": "已停用"}

# 状态机：只允许这些「当前状态 + 动作」组合。降级运行、已停用属于收尾状态，
# 不能直接办理入网回到正常运行；已停用是终态，不再接受任何动作。
TRANSITIONS = {
    ("待入网", "办理入网"): "正常运行",
    ("正常运行", "标记降级"): "降级运行",
    ("正常运行", "停用站点"): "已停用",
    ("降级运行", "停用站点"): "已停用",
}

# 待处理与异常量只由状态推导，概览看板、列表统计、详情页共用这一套口径：
# 降级与停用都计入异常量，待入网与降级运行计入待处理。
PENDING_STATUSES = {"待入网", "降级运行"}
ABNORMAL_STATUSES = {"降级运行", "已停用"}

ACTIONS_BY_STATUS: dict[str, list[str]] = {status: [] for status in STATUS_ORDER}
for _current, _action in TRANSITIONS:
    ACTIONS_BY_STATUS[_current].append(_action)


def derive_pending(status: str) -> bool:
    return status in PENDING_STATUSES


def derive_abnormal(status: str) -> bool:
    return status in ABNORMAL_STATUSES


class StationService:
    def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        """列表、详情、导出共用的展示口径：状态字段与可执行动作以当前状态为准。"""
        entry = dict(row)
        status = str(entry.get("status") or "")
        entry["站点状态"] = status
        entry["pending"] = derive_pending(status)
        entry["abnormal"] = derive_abnormal(status)
        entry["available_actions"] = list(ACTIONS_BY_STATUS.get(status, []))
        entry.setdefault("history", [])
        return entry

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
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._present(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = derive_pending(entry["status"])
        entry["abnormal"] = derive_abnormal(entry["status"])
        entry["history"] = []
        rows.append(entry)
        return self._present(entry), []

    def summary(self) -> dict[str, Any]:
        """按状态统计站点数，给列表页统计卡用，口径与概览看板一致。"""
        rows = store.rows(MODULE)
        by_status = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = str(row.get("status") or "")
            if status in by_status:
                by_status[status] += 1
        return {
            "by_status": by_status,
            "pending": sum(1 for row in rows if derive_pending(str(row.get("status") or ""))),
            "abnormal": sum(1 for row in rows if derive_abnormal(str(row.get("status") or ""))),
        }

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"观测站点 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测站点可执行范围"
        current = str(entry.get("status") or "")
        target = TRANSITIONS.get((current, action))
        if target is None:
            return None, f"观测站点当前状态为「{current}」，不允许执行「{action}」"
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        # 校验全部通过后才改动记录，失败或重复点击都不会留下半截状态
        entry["status"] = target
        entry["pending"] = derive_pending(target)
        entry["abnormal"] = derive_abnormal(target)
        entry.setdefault("history", []).append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "from": current,
            "to": target,
        })
        return self._present(entry), f"观测站点已{action}"
