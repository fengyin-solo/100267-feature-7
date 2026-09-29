"""特种车辆业务规则：出勤口径（年检/年限/燃油）、状态流转与记录留痕都收在这里。

出勤口径（调度出勤必须同时满足）：
1. 车辆状态为「待命」；已报废、维修中、出勤中的车不参与排班。
2. 年检在有效期内：年检到期前 15 天内或已经超期的，不允许出勤并说明原因。
3. 车辆年限不超过该车型上限。
4. 燃油量不低于该车型下限；低于下限的先补油再排。

不同车型的年限上限与燃油下限分开设置，见 TYPE_THRESHOLDS。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "vehicle"
DISPATCH_TABLE = "vehicle_dispatch"
MAINTENANCE_TABLE = "vehicle_maintenance"

REQUIRED_FIELDS = ["车辆编号", "车辆类型", "所属车队"]
STATUS_ORDER = ["待命", "出勤中", "维修中", "已报废"]

# 不同车型的判定阈值：年限上限（年）与燃油下限（升），分开设置
TYPE_THRESHOLDS: dict[str, dict[str, float]] = {
    "牵引车": {"max_age": 10, "min_fuel": 30},
    "客梯车": {"max_age": 12, "min_fuel": 25},
    "加油车": {"max_age": 8, "min_fuel": 40},
    "除冰车": {"max_age": 8, "min_fuel": 40},
    "摆渡车": {"max_age": 12, "min_fuel": 30},
    "行李车": {"max_age": 10, "min_fuel": 25},
    "清水排污车": {"max_age": 10, "min_fuel": 30},
    "航食配餐车": {"max_age": 10, "min_fuel": 30},
}
DEFAULT_THRESHOLD: dict[str, float] = {"max_age": 10, "min_fuel": 30}

INSPECTION_WARNING_DAYS = 15  # 年检到期前 15 天内不允许出勤
FUEL_TANK_CAPACITY = 100  # 补油时一次加满到 100 升

# 各状态对应的 pending/abnormal 口径，概览的待处理/异常量按此取数
_STATUS_FLAGS: dict[str, tuple[bool, bool]] = {
    "待命": (True, False),
    "出勤中": (True, True),
    "维修中": (False, False),
    "已报废": (False, True),
}


def _today() -> date:
    return date.today()


def _now_text() -> str:
    return datetime.now().strftime("%H:%M")


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class VehicleService:
    # ---------- 阈值 ----------
    def threshold_for(self, vehicle: dict[str, Any]) -> dict[str, float]:
        vtype = str(vehicle.get("车辆类型") or "").strip()
        return TYPE_THRESHOLDS.get(vtype, DEFAULT_THRESHOLD)

    # ---------- 出勤口径 ----------
    def check_eligibility(self, vehicle: dict[str, Any]) -> tuple[bool, list[str]]:
        """判断车辆能否出勤，返回 (是否可出勤, 原因列表)。原因用于拦截说明与前端展示。"""
        reasons: list[str] = []
        status = str(vehicle.get("status") or "")
        if status == "已报废":
            reasons.append("车辆已报废，不参与排班")
            return False, reasons
        if status == "维修中":
            reasons.append("车辆维修中，暂不能出勤")
            return False, reasons
        if status == "出勤中":
            reasons.append("车辆已出勤，尚未收车")
            return False, reasons

        threshold = self.threshold_for(vehicle)
        vtype = str(vehicle.get("车辆类型") or "该车型")

        # 年检：到期前 15 天内或已超期都不允许出勤
        inspection = _parse_date(vehicle.get("年检日期"))
        if inspection is None:
            reasons.append("年检日期缺失，无法核检出勤资格")
        else:
            today = _today()
            if inspection < today:
                reasons.append(f"年检已超期（{inspection.isoformat()}），不允许出勤")
            elif (inspection - today).days <= INSPECTION_WARNING_DAYS:
                reasons.append(f"年检即将到期（{inspection.isoformat()}，{INSPECTION_WARNING_DAYS} 天内），不允许出勤")

        # 车辆年限：不超过该车型上限
        age = _to_float(vehicle.get("车辆年限"))
        if age is None:
            reasons.append("车辆年限缺失，无法核检出勤资格")
        elif age > threshold["max_age"]:
            reasons.append(f"车辆年限 {age:g} 年超过{vtype}上限 {threshold['max_age']:g} 年")

        # 燃油：不低于该车型下限，低于下限先补油再排
        fuel = _to_float(vehicle.get("燃油量"))
        if fuel is None:
            reasons.append("燃油量缺失，无法核检出勤资格")
        elif fuel < threshold["min_fuel"]:
            reasons.append(
                f"燃油量 {fuel:g} 升低于{vtype}下限 {threshold['min_fuel']:g} 升，请先补油再排"
            )

        return (len(reasons) == 0), reasons

    def is_available(self, vehicle: dict[str, Any]) -> bool:
        """可用车辆：待命且通过出勤口径（年检/年限/燃油）。台账、出勤清单与概览共用此口径。"""
        if str(vehicle.get("status") or "") != "待命":
            return False
        ok, _ = self.check_eligibility(vehicle)
        return ok

    def available_vehicles(self) -> list[dict[str, Any]]:
        return [v for v in store.rows(MODULE) if self.is_available(v)]

    def available_count(self) -> int:
        return len(self.available_vehicles())

    def _enrich(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        """补充调度状态与不可调度原因，供前端展示。"""
        ok, reasons = self.check_eligibility(vehicle)
        status = str(vehicle.get("status") or "")
        if status == "待命":
            if ok:
                vehicle["调度状态"] = "可调度"
            else:
                non_fuel = [r for r in reasons if "燃油" not in r]
                vehicle["调度状态"] = "不可调度" if non_fuel else "需补油"
        elif status == "出勤中":
            vehicle["调度状态"] = "已出勤"
        elif status == "维修中":
            vehicle["调度状态"] = "维修中"
        elif status == "已报废":
            vehicle["调度状态"] = "已报废"
        else:
            vehicle["调度状态"] = status
        vehicle["可调度"] = ok
        vehicle["不可调度原因"] = reasons
        return vehicle

    def _sync_flags(self, vehicle: dict[str, Any]) -> None:
        status = str(vehicle.get("status") or "")
        pending, abnormal = _STATUS_FLAGS.get(status, (False, False))
        vehicle["pending"] = pending
        vehicle["abnormal"] = abnormal

    # ---------- 列表与明细 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._enrich(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("车辆编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        vehicle = store.find(MODULE, entry_id)
        if vehicle is None:
            return None
        return self._enrich(dict(vehicle))

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("车辆状态", "年检日期", "驾驶员", "燃油量", "车辆年限"):
            if field in values:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["车辆状态"] = STATUS_ORDER[0]
        self._sync_flags(entry)
        rows.append(entry)
        return self._enrich(dict(entry)), []

    # ---------- 动作 ----------
    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        vehicle = store.find(MODULE, entry_id)
        if vehicle is None:
            return None, f"特种车辆 {entry_id} 不存在或已归档"
        if action == "调度出勤":
            return self._dispatch(vehicle)
        if action == "补油":
            return self._refuel(vehicle)
        if action == "收车":
            return self._return_vehicle(vehicle)
        if action == "登记维修":
            return self._register_maintenance(vehicle)
        if action == "修竣":
            return self._complete_maintenance(vehicle)
        if action == "申请报废":
            return self._scrap(vehicle)
        return None, f"动作「{action}」不属于特种车辆可执行范围"

    def _dispatch(self, vehicle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(vehicle.get("status") or "")
        if status == "已报废":
            return None, "车辆已报废，不允许调度出勤"
        if status == "维修中":
            return None, "车辆维修中，不允许调度出勤"
        if status == "出勤中":
            return None, "车辆已出勤，请勿重复调度；如需收回请执行收车"
        ok, reasons = self.check_eligibility(vehicle)
        if not ok:
            non_fuel = [r for r in reasons if "燃油" not in r]
            if non_fuel:
                return None, "调度出勤被拦截：" + "；".join(non_fuel)
            return None, "调度出勤被拦截：" + "；".join(reasons) + "。请先补油后再调度出勤"

        vehicle["status"] = "出勤中"
        vehicle["车辆状态"] = "出勤中"
        self._sync_flags(vehicle)
        record = {
            "id": self._next_aux_id(DISPATCH_TABLE),
            "车辆编号": vehicle.get("车辆编号"),
            "车辆类型": vehicle.get("车辆类型"),
            "出勤日期": _today().isoformat(),
            "出车时间": _now_text(),
            "收车时间": None,
            "状态": "出勤中",
        }
        store.aux_rows(DISPATCH_TABLE).append(record)
        return self._enrich(dict(vehicle)), f"特种车辆 {vehicle.get('车辆编号')} 已调度出勤"

    def _refuel(self, vehicle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(vehicle.get("status") or "")
        if status == "已报废":
            return None, "车辆已报废，无需补油"
        before = _to_float(vehicle.get("燃油量")) or 0
        vehicle["燃油量"] = FUEL_TANK_CAPACITY
        if status == "待命":
            # 补油后仍待命，若已满足出勤口径则可继续排车
            self._sync_flags(vehicle)
            return self._enrich(dict(vehicle)), (
                f"特种车辆 {vehicle.get('车辆编号')} 已补油，燃油量 {before:g} → {FUEL_TANK_CAPACITY:g} 升，可继续调度出勤"
            )
        return self._enrich(dict(vehicle)), (
            f"特种车辆 {vehicle.get('车辆编号')} 已补油，燃油量 {before:g} → {FUEL_TANK_CAPACITY:g} 升"
        )

    def _return_vehicle(self, vehicle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(vehicle.get("status") or "")
        if status != "出勤中":
            return None, f"车辆当前为「{status or '未知'}」，无需收车"
        vehicle["status"] = "待命"
        vehicle["车辆状态"] = "待命"
        self._sync_flags(vehicle)
        # 收车后保留原排班记录，只补收车时间与状态
        record = self._find_active_dispatch(vehicle)
        if record is not None:
            record["收车时间"] = _now_text()
            record["状态"] = "已收车"
        return self._enrich(dict(vehicle)), f"特种车辆 {vehicle.get('车辆编号')} 已收车，排班记录已保留"

    def _register_maintenance(self, vehicle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(vehicle.get("status") or "")
        if status == "已报废":
            return None, "车辆已报废，不参与排班与维修登记"
        vehicle["status"] = "维修中"
        vehicle["车辆状态"] = "维修中"
        self._sync_flags(vehicle)
        # 同一辆车的维修记录重复登记只留最近一次
        rows = store.aux_rows(MAINTENANCE_TABLE)
        rows[:] = [row for row in rows if row.get("车辆编号") != vehicle.get("车辆编号")]
        record = {
            "id": self._next_aux_id(MAINTENANCE_TABLE),
            "车辆编号": vehicle.get("车辆编号"),
            "维修日期": _today().isoformat(),
            "维修内容": "例行保养",
            "状态": "维修中",
        }
        rows.append(record)
        return self._enrich(dict(vehicle)), f"特种车辆 {vehicle.get('车辆编号')} 已登记维修（仅保留最近一次维修记录）"

    def _complete_maintenance(self, vehicle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(vehicle.get("status") or "")
        if status != "维修中":
            return None, f"车辆当前为「{status or '未知'}」，无在修记录"
        vehicle["status"] = "待命"
        vehicle["车辆状态"] = "待命"
        self._sync_flags(vehicle)
        rows = store.aux_rows(MAINTENANCE_TABLE)
        for row in rows:
            if row.get("车辆编号") == vehicle.get("车辆编号"):
                row["状态"] = "已修竣"
        return self._enrich(dict(vehicle)), f"特种车辆 {vehicle.get('车辆编号')} 维修完成，已回到待命"

    def _scrap(self, vehicle: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        vehicle["status"] = "已报废"
        vehicle["车辆状态"] = "已报废"
        self._sync_flags(vehicle)
        return self._enrich(dict(vehicle)), f"特种车辆 {vehicle.get('车辆编号')} 已申请报废，不再参与排班"

    # ---------- 出勤记录与维修记录 ----------
    def _next_aux_id(self, table: str) -> int:
        rows = store.aux_rows(table)
        return max((int(row.get("id", 0)) for row in rows), default=0) + 1

    def _find_active_dispatch(self, vehicle: dict[str, Any]) -> dict[str, Any] | None:
        for row in store.aux_rows(DISPATCH_TABLE):
            if row.get("车辆编号") == vehicle.get("车辆编号") and row.get("状态") == "出勤中":
                return row
        return None

    def dispatch_records(self, *, today_only: bool = True) -> list[dict[str, Any]]:
        """出勤清单：默认只看当日出勤记录。导出当日出勤单与此处共用同一份数据。"""
        rows = [dict(row) for row in store.aux_rows(DISPATCH_TABLE)]
        if today_only:
            today = _today().isoformat()
            rows = [row for row in rows if str(row.get("出勤日期") or "") == today]
        rows.sort(key=lambda row: int(row.get("id", 0)))
        return rows

    def maintenance_records(self) -> list[dict[str, Any]]:
        """维修记录：每辆车只保留最近一次登记。"""
        rows = [dict(row) for row in store.aux_rows(MAINTENANCE_TABLE)]
        rows.sort(key=lambda row: int(row.get("id", 0)))
        return rows

    def stats(self) -> dict[str, int]:
        """车辆台账顶部统计：可用、待命、出勤、维修、报废。"""
        rows = store.rows(MODULE)
        return {
            "可用车辆": self.available_count(),
            "待命车辆": sum(1 for v in rows if str(v.get("status")) == "待命"),
            "出勤车辆": sum(1 for v in rows if str(v.get("status")) == "出勤中"),
            "维修车辆": sum(1 for v in rows if str(v.get("status")) == "维修中"),
            "报废车辆": sum(1 for v in rows if str(v.get("status")) == "已报废"),
        }
