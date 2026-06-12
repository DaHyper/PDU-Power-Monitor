from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RackStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class PduStatus(str, Enum):
    OK = "ok"
    UNREACHABLE = "unreachable"
    STALE = "stale"


@dataclass
class PduReading:
    name: str
    host: str
    power_kw: float | None
    energy_kwh: float | None
    status: PduStatus
    last_poll: datetime | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "host": self.host,
            "power_kw": self.power_kw,
            "energy_kwh": self.energy_kwh,
            "status": self.status.value,
            "last_poll": self.last_poll.isoformat() if self.last_poll else None,
            "error": self.error,
        }


@dataclass
class RackReading:
    name: str
    description: str
    power_kw: float | None
    warning_kw: float
    critical_kw: float
    status: RackStatus
    pdus: list[PduReading] = field(default_factory=list)
    headroom_kw: float | None = None
    percent_of_limit: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "power_kw": self.power_kw,
            "warning_kw": self.warning_kw,
            "critical_kw": self.critical_kw,
            "status": self.status.value,
            "headroom_kw": self.headroom_kw,
            "percent_of_limit": self.percent_of_limit,
            "pdus": [p.to_dict() for p in self.pdus],
        }


@dataclass
class DashboardState:
    racks: list[RackReading] = field(default_factory=list)
    last_poll: datetime | None = None
    poll_interval_seconds: int = 60
    history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    maintenance_enabled: bool = False
    maintenance_message: str = ""
    alerts_silenced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "racks": [r.to_dict() for r in self.racks],
            "last_poll": self.last_poll.isoformat() if self.last_poll else None,
            "poll_interval_seconds": self.poll_interval_seconds,
            "history": self.history,
            "maintenance_enabled": self.maintenance_enabled,
            "maintenance_message": self.maintenance_message,
            "alerts_silenced": self.alerts_silenced,
        }
