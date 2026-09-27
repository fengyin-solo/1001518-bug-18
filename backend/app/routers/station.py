"""观测站点接口：维护观测站点，覆盖办理入网、标记降级、停用站点等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.station import StationService

router = APIRouter(prefix="/api/station", tags=["观测站点"])

service = StationService()

LIST_FIELDS = ["站点编码", "站点名称", "站点类别", "经纬度坐标", "海拔高度", "建站年份", "值守方式", "站点状态"]
STATUSES = ["待入网", "正常运行", "降级运行", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按站点编码检索"),
    status: str | None = Query(default=None, description="待入网、正常运行、降级运行、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按站点编码与状态过滤观测站点列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def station_stats() -> dict[str, int]:
    """列表统计卡：在网、降级、停用及待处理、异常量，口径与概览看板完全一致。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出观测站点清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "station", "total": total, "items": items}


@router.get("/{entry_id}/history")
def action_history(entry_id: int) -> dict[str, Any]:
    """读取单个站点的操作记录，最近一次在最前；站点不存在时明确报错。"""
    records = service.history(entry_id)
    if records is None:
        raise HTTPException(status_code=404, detail=f"观测站点 {entry_id} 不存在或已归档")
    return {"entry_id": entry_id, "total": len(records), "items": records}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条观测站点明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测站点 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条观测站点，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="观测站点已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条观测站点执行办理入网、标记降级、停用站点。

    业务不允许的流转（如收尾态直接入网、重复点击同一动作）会被拦下并说明原因，
    此时 ok=false 且状态不变，前端必须按 ok 判定而不是只看 HTTP 200。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, operator=payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
