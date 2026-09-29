"""特种车辆接口：维护特种车辆，覆盖调度出勤、补油、收车、登记维修、申请报废等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.vehicle import VehicleService

router = APIRouter(prefix="/api/vehicle", tags=["特种车辆"])

service = VehicleService()

LIST_FIELDS = ["车辆编号", "车辆类型", "所属车队", "车辆状态", "年检日期", "车辆年限", "驾驶员", "燃油量", "调度状态"]
STATUSES = ["待命", "出勤中", "维修中", "已报废"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按车辆编号检索"),
    status: str | None = Query(default=None, description="待命、出勤中、维修中、已报废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按车辆编号与状态过滤特种车辆列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def vehicle_stats() -> dict[str, int]:
    """车辆台账统计：可用车辆数与各状态车辆数，与出勤清单、运营概览同口径。"""
    return service.stats()


@router.get("/dispatch-records")
def dispatch_records(
    today_only: bool = Query(default=True, description="只看当日出勤记录"),
) -> dict[str, Any]:
    """出勤清单：当日出勤记录。导出当日出勤单与此处共用同一份数据，车辆数一致。"""
    items = service.dispatch_records(today_only=today_only)
    return {"items": items, "total": len(items)}


@router.get("/maintenance-records")
def maintenance_records() -> dict[str, Any]:
    """维修记录：同一辆车只保留最近一次登记。"""
    items = service.maintenance_records()
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出特种车辆清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "vehicle", "total": total, "items": items}


@router.get("/export-dispatch")
def export_dispatch() -> dict[str, Any]:
    """导出当日出勤单：车辆数与出勤清单对得上。"""
    items = service.dispatch_records(today_only=True)
    return {"module": "vehicle-dispatch", "total": len(items), "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条特种车辆明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"特种车辆 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条特种车辆，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="特种车辆已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条特种车辆执行调度出勤、补油、收车、登记维修、修竣、申请报废；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
