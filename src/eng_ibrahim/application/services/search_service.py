"""Global search (SPEC 3.6, Ctrl+K): one query across assets, vehicles, work orders, parts.

Each list service already applies the Arabic search normalisation (SPEC 4.5), so this
only fans the query out and caps each group.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...infrastructure.database.engine import Database
from .asset_service import AssetService
from .inventory_service import InventoryService
from .vehicle_service import VehicleService
from .work_order_service import WorkOrderService

MIN_QUERY = 2
PER_KIND = 8


@dataclass(frozen=True)
class SearchHit:
    kind: str  # "asset" | "vehicle" | "work_order" | "part"
    record_id: str
    code: str
    title: str
    detail: str


class SearchService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def search(self, query: str, arabic: bool = True) -> list[SearchHit]:
        query = (query or "").strip()
        if len(query) < MIN_QUERY:
            return []
        hits: list[SearchHit] = []
        vehicles = VehicleService(self._db).list(query=query)
        vehicle_ids = {v.asset_id for v in VehicleService(self._db).list()}
        for v in vehicles[:PER_KIND]:
            hits.append(SearchHit("vehicle", v.asset_id, v.fleet_code, v.name(arabic),
                                  v.plate_number or ""))
        # Vehicles are assets too; they are listed once, under the vehicles screen.
        assets = [a for a in AssetService(self._db).list(query=query)
                  if a.id not in vehicle_ids]
        for a in assets[:PER_KIND]:
            hits.append(SearchHit("asset", a.id, a.code, a.name(arabic), a.location))
        for wo in WorkOrderService(self._db).list(query=query)[:PER_KIND]:
            hits.append(SearchHit("work_order", wo.id, wo.number, wo.title, wo.asset_code))
        for part in InventoryService(self._db).list_parts(query=query)[:PER_KIND]:
            hits.append(SearchHit("part", part.id, part.code, part.name(arabic),
                                  part.available))
        return hits
