"""特种车辆业务规则：出勤判定口径、状态流转、维修记录去重都收在这里。

出勤口径（调度出勤前逐条校验，任一不满足即拦截并说明原因）：
- 状态：已报废不参与排班；维修中、出勤中的车辆不能重复派车；
- 年检：年检到期前 15 天内（窗口可按车型调整）或已经超期的车辆不允许出勤；
- 车龄：按投入使用日期核算，超过车型年限上限的不允许出勤；
- 燃油：燃油量低于车型下限的先补油再排班。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "vehicle"
DISPATCH_MODULE = "vehicle_dispatch"
MAINTENANCE_MODULE = "vehicle_maintenance"

REQUIRED_FIELDS = ["车辆编号", "车辆类型", "所属车队"]
STATUS_ORDER = ["待命", "出勤中", "维修中", "已报废"]
ACTIONS = ["调度出勤", "收车", "补油", "登记维修", "完成维修", "申请报废"]

# 默认判定口径：年检临期窗口 15 天，未单独配置的车型按这套阈值执行。
DEFAULT_THRESHOLD: dict[str, Any] = {"fuel_min": 20.0, "max_age_years": 10, "inspection_window_days": 15}

# 不同车型的判定阈值分开设置：燃油下限(%)、车龄上限(年)、年检临期窗口(天)。
TYPE_THRESHOLDS: dict[str, dict[str, Any]] = {
    "牵引车": {"fuel_min": 30.0, "max_age_years": 12, "inspection_window_days": 15},
    "摆渡车": {"fuel_min": 25.0, "max_age_years": 10, "inspection_window_days": 15},
    "加油车": {"fuel_min": 20.0, "max_age_years": 15, "inspection_window_days": 15},
    "除冰车": {"fuel_min": 35.0, "max_age_years": 8, "inspection_window_days": 15},
    "平台车": {"fuel_min": 25.0, "max_age_years": 10, "inspection_window_days": 15},
    "食品车": {"fuel_min": 20.0, "max_age_years": 10, "inspection_window_days": 15},
}


def threshold_for(vehicle_type: str) -> dict[str, Any]:
    """按车型取判定阈值；没单独配置的车型回落到默认口径。"""
    merged = dict(DEFAULT_THRESHOLD)
    merged.update(TYPE_THRESHOLDS.get(vehicle_type, {}))
    return merged


def _parse_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_float(raw: Any) -> float | None:
    try:
        return float(str(raw).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def vehicle_age_years(entry: dict[str, Any], today: date) -> float | None:
    """按投入使用日期核算车龄；日期缺失时返回 None，由判定口径拦截。"""
    start = _parse_date(entry.get("投入使用日期"))
    if start is None:
        return None
    return max((today - start).days, 0) / 365.25


def evaluate_dispatch(entry: dict[str, Any], today: date) -> list[str]:
    """出勤判定：返回不允许出勤的原因列表，空列表表示可以调度出勤。"""
    reasons: list[str] = []
    status = str(entry.get("status") or "")
    if status == "已报废":
        reasons.append("车辆已报废，不参与排班")
    elif status == "维修中":
        reasons.append("车辆维修中，完成维修后才能排班")
    elif status == "出勤中":
        reasons.append("车辆正在出勤，收车后才能再次调度")

    vehicle_type = str(entry.get("车辆类型") or "")
    rule = threshold_for(vehicle_type)

    inspection = _parse_date(entry.get("年检日期"))
    if inspection is None:
        reasons.append("年检日期缺失或格式不正确")
    else:
        days_left = (inspection - today).days
        window = int(rule["inspection_window_days"])
        if days_left < 0:
            reasons.append(f"年检已于{inspection.isoformat()}超期{-days_left}天，不允许出勤")
        elif days_left <= window:
            reasons.append(f"年检{inspection.isoformat()}到期前{window}天内（剩{days_left}天），不允许出勤")

    age = vehicle_age_years(entry, today)
    if age is None:
        reasons.append("投入使用日期缺失或格式不正确，无法核算车龄")
    elif age > float(rule["max_age_years"]):
        reasons.append(f"车龄{age:.1f}年超过{vehicle_type}上限{rule['max_age_years']}年，不允许出勤")

    fuel = _parse_float(entry.get("燃油量"))
    if fuel is None:
        reasons.append("燃油量未登记，先补油再排班")
    elif fuel < float(rule["fuel_min"]):
        reasons.append(f"燃油量{fuel:g}%低于{vehicle_type}下限{rule['fuel_min']:g}%，需先补油再排班")
    return reasons


def fleet_summary(today: date | None = None) -> dict[str, int]:
    """车队汇总：可用车辆数的唯一口径，台账、出勤清单、运营概览都从这里取数。"""
    today = today or date.today()
    summary = {"total": 0, "available": 0, "on_duty": 0, "maintenance": 0, "scrapped": 0, "blocked": 0}
    for row in store.rows(MODULE):
        summary["total"] += 1
        status = row.get("status")
        if status == "已报废":
            summary["scrapped"] += 1
        elif status == "出勤中":
            summary["on_duty"] += 1
        elif status == "维修中":
            summary["maintenance"] += 1
        elif status == "待命":
            if evaluate_dispatch(row, today):
                summary["blocked"] += 1
            else:
                summary["available"] += 1
    return summary


def _overview_extras(_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """运营概览注入：可用车辆数与台账、出勤清单保持同一口径。"""
    summary = fleet_summary()
    return {
        "pending": summary["available"] + summary["blocked"],
        "abnormal": summary["blocked"] + summary["maintenance"],
        "cards": [
            {"label": "可用车辆", "value": summary["available"]},
            {"label": "出勤中车辆", "value": summary["on_duty"]},
        ],
    }


store.mark_auxiliary(DISPATCH_MODULE)
store.mark_auxiliary(MAINTENANCE_MODULE)
store.register_overview_extras(MODULE, _overview_extras)


class VehicleService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        today = date.today()
        rows = store.rows(MODULE)
        for row in rows:
            self._enrich(row, today)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("车辆编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            self._enrich(entry, date.today())
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + ["驾驶员", "年检日期", "投入使用日期"]:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = str(value).strip()
        entry["燃油量"] = _parse_float(values.get("燃油量")) if values.get("燃油量") not in (None, "") else 100.0
        entry["status"] = STATUS_ORDER[0]
        entry["调度状态"] = "未派车"
        rows.append(entry)
        self._enrich(entry, date.today())
        return entry, []

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"特种车辆 {entry_id} 不存在或已归档"
        handlers = {
            "调度出勤": self._dispatch,
            "收车": self._return_vehicle,
            "补油": self._refuel,
            "登记维修": self._register_maintenance,
            "完成维修": self._finish_maintenance,
            "申请报废": self._scrap,
        }
        handler = handlers.get(action)
        if handler is None:
            return None, f"动作「{action}」不属于特种车辆可执行范围"
        entry, message = handler(entry, values or {})
        if entry is not None:
            self._enrich(entry, date.today())
        return entry, message

    def fleet_summary(self) -> dict[str, int]:
        return fleet_summary()

    def list_thresholds(self) -> dict[str, Any]:
        return {"default": dict(DEFAULT_THRESHOLD), "types": {k: dict(v) for k, v in sorted(TYPE_THRESHOLDS.items())}}

    def update_threshold(self, vehicle_type: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        vehicle_type = vehicle_type.strip()
        if not vehicle_type:
            return None, "车型名称不能为空"
        updated = dict(threshold_for(vehicle_type))
        for field in ("fuel_min", "max_age_years", "inspection_window_days"):
            raw = values.get(field)
            if raw is None:
                continue
            number = _parse_float(raw)
            if number is None or number < 0:
                return None, f"阈值「{field}」必须是不小于 0 的数字"
            updated[field] = int(number) if field != "fuel_min" else number
        TYPE_THRESHOLDS[vehicle_type] = updated
        return dict(updated), f"车型「{vehicle_type}」的判定阈值已更新"

    def dispatch_sheet(self, day: str | None = None) -> tuple[str, list[dict[str, Any]]]:
        """当日出勤清单：排班记录独立成表，收车只改状态不删记录，刷新后仍然保留。"""
        day = (day or date.today().isoformat()).strip() or date.today().isoformat()
        records = [row for row in store.rows(DISPATCH_MODULE) if str(row.get("出勤日期")) == day]
        records.sort(key=lambda row: int(row.get("id", 0)))
        return day, records

    def dispatch_csv(self, day: str | None = None) -> tuple[str, str]:
        """导出当日出勤单：与出勤清单同源，单上的车辆数必然对得上。"""
        day, records = self.dispatch_sheet(day)
        headers = ["单号", "车辆编号", "车辆类型", "驾驶员", "出勤日期", "出勤时间", "收车时间", "状态"]
        lines = [",".join(headers)]
        for record in records:
            lines.append(",".join(str(record.get(field) or "") for field in headers))
        return day, "\ufeff" + "\n".join(lines)

    def list_maintenance(self) -> list[dict[str, Any]]:
        """维修记录：同一辆车重复登记只保留最近一次（按登记时间取最新）。"""
        latest: dict[int, dict[str, Any]] = {}
        for row in store.rows(MAINTENANCE_MODULE):
            key = int(row.get("车辆id", 0))
            current = latest.get(key)
            if current is None or str(row.get("登记时间", "")) >= str(current.get("登记时间", "")):
                latest[key] = row
        return sorted(latest.values(), key=lambda row: int(row.get("id", 0)))

    def _enrich(self, entry: dict[str, Any], today: date) -> None:
        """给台账行补上展示与概览用的派生字段，同时刷新 pending/abnormal 标记。"""
        reasons = evaluate_dispatch(entry, today)
        age = vehicle_age_years(entry, today)
        entry["车龄"] = round(age, 1) if age is not None else None
        entry["可出勤"] = not reasons
        entry["出勤判定"] = "可出勤" if not reasons else "；".join(reasons)
        status = entry.get("status")
        entry["pending"] = status == "待命"
        entry["abnormal"] = (status == "待命" and bool(reasons)) or status == "维修中"

    def _dispatch(self, entry: dict[str, Any], _values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        today = date.today()
        reasons = evaluate_dispatch(entry, today)
        if reasons:
            return None, "；".join(reasons)
        day = today.isoformat()
        rows = store.rows(DISPATCH_MODULE)
        seq = sum(1 for row in rows if str(row.get("出勤日期")) == day) + 1
        record = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "单号": f"DISP-{day.replace('-', '')}-{seq:03d}",
            "车辆id": entry["id"],
            "车辆编号": entry.get("车辆编号"),
            "车辆类型": entry.get("车辆类型"),
            "驾驶员": entry.get("驾驶员"),
            "出勤日期": day,
            "出勤时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "收车时间": None,
            "状态": "出勤中",
            "pending": True,
            "abnormal": False,
        }
        rows.append(record)
        entry["status"] = "出勤中"
        entry["调度状态"] = "已派车"
        return entry, f"特种车辆已调度出勤，出勤单号 {record['单号']}"

    def _return_vehicle(self, entry: dict[str, Any], _values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != "出勤中":
            return None, "车辆当前不在出勤状态，无需收车"
        open_records = [
            row for row in store.rows(DISPATCH_MODULE)
            if int(row.get("车辆id", 0)) == int(entry["id"]) and row.get("状态") == "出勤中"
        ]
        if open_records:
            record = max(open_records, key=lambda row: int(row.get("id", 0)))
            record["状态"] = "已收车"
            record["收车时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record["pending"] = False
        entry["status"] = "待命"
        entry["调度状态"] = "未派车"
        return entry, "车辆已收车，当日排班记录保留在出勤清单里"

    def _refuel(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = entry.get("status")
        if status == "已报废":
            return None, "车辆已报废，不再安排补油"
        if status == "出勤中":
            return None, "车辆出勤中，收车后再补油"
        target = _parse_float(values.get("燃油量"))
        if target is None:
            target = 100.0
        if not 0 < target <= 100:
            return None, "补油后的燃油量要在 0 到 100 之间"
        entry["燃油量"] = target
        return entry, f"已补油至 {target:g}%，可重新参与排班"

    def _register_maintenance(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = entry.get("status")
        if status == "出勤中":
            return None, "车辆出勤中，收车后才能登记维修"
        if status == "已报废":
            return None, "车辆已报废，无需登记维修"
        rows = store.rows(MAINTENANCE_MODULE)
        # 同一辆车的维修记录重复登记只留最近一次：先清掉旧记录再写入。
        rows[:] = [row for row in rows if int(row.get("车辆id", 0)) != int(entry["id"])]
        rows.append({
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "车辆id": entry["id"],
            "车辆编号": entry.get("车辆编号"),
            "维修日期": date.today().isoformat(),
            "维修内容": str(values.get("维修内容") or "例行检修").strip() or "例行检修",
            "登记时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "经办人": str(values.get("经办人") or "调度室").strip() or "调度室",
            "pending": True,
            "abnormal": False,
        })
        entry["status"] = "维修中"
        return entry, "已登记维修，同车旧记录已合并，仅保留最近一次"

    def _finish_maintenance(self, entry: dict[str, Any], _values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != "维修中":
            return None, "车辆当前不在维修状态"
        entry["status"] = "待命"
        return entry, "维修完成，车辆恢复待命"

    def _scrap(self, entry: dict[str, Any], _values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = entry.get("status")
        if status == "已报废":
            return None, "车辆已是报废状态"
        if status == "出勤中":
            return None, "车辆出勤中，收车后才能申请报废"
        entry["status"] = "已报废"
        entry["调度状态"] = "未派车"
        return entry, "车辆已报废，不再参与排班"
