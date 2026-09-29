"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # 业务流水：不出现在模块概览里，只由对应业务模块读写
        today = date.today().isoformat()
        self._aux: dict[str, list[dict[str, Any]]] = {
            "vehicle_dispatch": [
                {"id": 1, "车辆编号": "VEHI-0002", "车辆类型": "加油车", "出勤日期": today,
                 "出车时间": "08:30", "收车时间": None, "状态": "出勤中"},
            ],
            "vehicle_maintenance": [
                {"id": 1, "车辆编号": "VEHI-0003", "维修日期": today,
                 "维修内容": "例行保养", "状态": "维修中"},
            ],
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def aux_rows(self, name: str) -> list[dict[str, Any]]:
        return self._aux.setdefault(name, [])

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            entry = {
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            }
            if name == "vehicle":
                # 可用车辆数只由特种车辆业务规则决定，台账、出勤清单与概览共用同一口径
                from app.services.vehicle import VehicleService
                entry["available"] = VehicleService().available_count()
            else:
                entry["available"] = 0
            modules.append(entry)
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
