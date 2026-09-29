"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any, Callable

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._auxiliary: set[str] = set()
        self._overview_extras: dict[str, Callable[[list[dict[str, Any]]], dict[str, Any]]] = {}

    def mark_auxiliary(self, module: str) -> None:
        """把模块标记为内部表：数据照常存取，但不计入运营概览的业务模块清单。"""
        self._auxiliary.add(module)

    def register_overview_extras(
        self,
        module: str,
        provider: Callable[[list[dict[str, Any]]], dict[str, Any]],
    ) -> None:
        """允许业务模块向运营概览注入自己的待处理/异常口径与额外卡片。"""
        self._overview_extras[module] = provider

    def module_names(self) -> list[str]:
        return sorted(name for name in self._tables if name not in self._auxiliary)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        extra_cards: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            pending = sum(1 for row in rows if row.get("pending"))
            abnormal = sum(1 for row in rows if row.get("abnormal"))
            provider = self._overview_extras.get(name)
            if provider is not None:
                extras = provider(rows)
                pending = int(extras.get("pending", pending))
                abnormal = int(extras.get("abnormal", abnormal))
                extra_cards.extend(extras.get("cards", []))
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": pending,
                "abnormal": abnormal,
            })
        cards: list[dict[str, object]] = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        cards.extend(extra_cards)
        return {"cards": cards, "modules": modules}


store = Store()
