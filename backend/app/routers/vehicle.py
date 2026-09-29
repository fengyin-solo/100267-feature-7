"""特种车辆接口：车辆台账、出勤判定、当日出勤清单与出勤单导出。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.vehicle import VehicleService

router = APIRouter(prefix="/api/vehicle", tags=["特种车辆"])

service = VehicleService()

STATUSES = ["待命", "出勤中", "维修中", "已报废"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按车辆编号检索"),
    status: str | None = Query(default=None, description="待命、出勤中、维修中、已报废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按车辆编号与状态过滤特种车辆列表；每行附带车龄与出勤判定说明。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def fleet_summary() -> dict[str, int]:
    """车队汇总：可用车辆数的统一口径，台账、出勤清单、运营概览共用。"""
    return service.fleet_summary()


@router.get("/thresholds")
def list_thresholds() -> dict[str, Any]:
    """读取分车型的出勤判定阈值（燃油下限、车龄上限、年检临期窗口）。"""
    return service.list_thresholds()


@router.put("/thresholds/{vehicle_type}", response_model=ActionResult)
def update_threshold(vehicle_type: str, payload: EntryPayload) -> ActionResult:
    """按车型单独设置判定阈值；非法取值会被拦下并说明原因。"""
    threshold, message = service.update_threshold(vehicle_type, payload.values)
    if threshold is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=threshold)


@router.get("/dispatch")
def dispatch_sheet(day: str | None = Query(default=None, description="出勤日期，默认今天")) -> dict[str, Any]:
    """当日出勤清单：排班记录持久保存，收车后刷新仍然保留。"""
    day, records = service.dispatch_sheet(day)
    return {"date": day, "total": len(records), "items": records, "summary": service.fleet_summary()}


@router.get("/dispatch/export")
def export_dispatch_sheet(day: str | None = Query(default=None, description="出勤日期，默认今天")) -> Response:
    """导出当日出勤单（CSV）：与出勤清单同源，单上的车辆数必然对得上。"""
    day, csv_text = service.dispatch_csv(day)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=dispatch-{day}.csv"},
    )


@router.get("/maintenance")
def list_maintenance() -> dict[str, Any]:
    """维修记录：同一辆车重复登记只保留最近一次。"""
    records = service.list_maintenance()
    return {"total": len(records), "items": records}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出特种车辆台账：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "vehicle", "total": total, "items": items}


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
    """执行调度出勤、收车、补油、登记维修、完成维修、申请报废；不满足出勤口径会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
