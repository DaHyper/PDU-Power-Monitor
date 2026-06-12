from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from rack_power_monitor.alerts import AlertNotifier
from rack_power_monitor.config import AppConfig, PduConfig, RackConfig, load_config
from rack_power_monitor.models import DashboardState, PduReading, PduStatus, RackReading, RackStatus
from rack_power_monitor.snmp_client import poll_pdu_power_energy

logger = logging.getLogger(__name__)


class AlertTracker:
    """Tracks alert state and enforces cooldown between repeat notifications."""

    def __init__(self, cooldown_minutes: int) -> None:
        self.cooldown_seconds = cooldown_minutes * 60
        self._rack_state: dict[str, RackStatus] = {}
        self._pdu_state: dict[str, PduStatus] = {}
        self._last_sent: dict[str, float] = {}

    def _key(self, prefix: str, name: str, status: str) -> str:
        return f"{prefix}:{name}:{status}"

    def _can_send(self, key: str) -> bool:
        last = self._last_sent.get(key, 0)
        return (time.monotonic() - last) >= self.cooldown_seconds

    def _mark_sent(self, key: str) -> None:
        self._last_sent[key] = time.monotonic()

    def process(
        self,
        racks: list[RackReading],
        notifier: AlertNotifier,
    ) -> None:
        for rack in racks:
            prev = self._rack_state.get(rack.name, RackStatus.UNKNOWN)
            curr = rack.status

            if curr in (RackStatus.WARNING, RackStatus.CRITICAL) and curr != prev:
                key = self._key("rack", rack.name, curr.value)
                if self._can_send(key):
                    level = "WARNING" if curr == RackStatus.WARNING else "CRITICAL"
                    severity = "warning" if curr == RackStatus.WARNING else "critical"
                    notifier.send(
                        subject=f"[Rack Power Monitor] {level}: {rack.name} at {rack.power_kw:.2f} kW",
                        body=(
                            f"Rack {rack.name} has crossed the {level.lower()} threshold.\n\n"
                            f"Current draw: {rack.power_kw:.2f} kW\n"
                            f"Warning threshold: {rack.warning_kw:.2f} kW\n"
                            f"Critical threshold: {rack.critical_kw:.2f} kW\n"
                        ),
                        severity=severity,
                    )
                    self._mark_sent(key)

            if prev in (RackStatus.WARNING, RackStatus.CRITICAL) and curr == RackStatus.OK:
                key = self._key("rack", rack.name, "recovery")
                if self._can_send(key):
                    notifier.send(
                        subject=f"[Rack Power Monitor] RECOVERED: {rack.name} back to normal",
                        body=(
                            f"Rack {rack.name} is back under the warning threshold.\n\n"
                            f"Current draw: {rack.power_kw:.2f} kW\n"
                        ),
                        severity="recovery",
                    )
                    self._mark_sent(key)

            self._rack_state[rack.name] = curr

            for pdu in rack.pdus:
                pdu_key = f"{rack.name}:{pdu.host}"
                prev_pdu = self._pdu_state.get(pdu_key, PduStatus.OK)
                curr_pdu = pdu.status

                if curr_pdu == PduStatus.UNREACHABLE and prev_pdu == PduStatus.OK:
                    key = self._key("pdu", pdu_key, "unreachable")
                    if self._can_send(key):
                        notifier.send(
                            subject=f"[Rack Power Monitor] PDU UNREACHABLE: {pdu.name} ({pdu.host})",
                            body=(
                                f"PDU {pdu.name} at {pdu.host} is unreachable.\n"
                                f"Rack: {rack.name}\n"
                                f"Error: {pdu.error or 'timeout'}\n"
                            ),
                            severity="critical",
                        )
                        self._mark_sent(key)

                if curr_pdu == PduStatus.OK and prev_pdu == PduStatus.UNREACHABLE:
                    key = self._key("pdu", pdu_key, "recovery")
                    if self._can_send(key):
                        notifier.send(
                            subject=f"[Rack Power Monitor] PDU RECOVERED: {pdu.name} ({pdu.host})",
                            body=f"PDU {pdu.name} at {pdu.host} is responding again.",
                            severity="recovery",
                        )
                        self._mark_sent(key)

                self._pdu_state[pdu_key] = curr_pdu


class HistoryBuffer:
    """Ring buffer of rack power readings for sparkline display."""

    def __init__(self, max_points: int = 1440) -> None:
        self.max_points = max_points
        self._data: dict[str, deque[dict[str, Any]]] = {}

    def add(self, rack_name: str, power_kw: float | None, timestamp: datetime) -> None:
        if rack_name not in self._data:
            self._data[rack_name] = deque(maxlen=self.max_points)
        self._data[rack_name].append(
            {
                "t": timestamp.isoformat(),
                "kw": power_kw,
            }
        )

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {name: list(points) for name, points in self._data.items()}


class Poller:
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self._config = load_config(config_path)
        self._lock = threading.Lock()
        self._state = DashboardState(poll_interval_seconds=self._config.poll_interval_seconds)
        self._history = HistoryBuffer()
        self._alert_tracker = AlertTracker(self._config.alert_cooldown_minutes)
        self._last_pdu_readings: dict[str, PduReading] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._init_state_from_config()

    @property
    def config(self) -> AppConfig:
        with self._lock:
            return self._config

    def get_state(self) -> DashboardState:
        with self._lock:
            return DashboardState(
                racks=list(self._state.racks),
                last_poll=self._state.last_poll,
                poll_interval_seconds=self._state.poll_interval_seconds,
                history=self._history.snapshot(),
            )

    def reload_config(self) -> None:
        with self._lock:
            self._config = load_config(self.config_path)
            self._state.poll_interval_seconds = self._config.poll_interval_seconds
            self._alert_tracker.cooldown_seconds = self._config.alert_cooldown_minutes * 60
            self._init_state_from_config()

    def _init_state_from_config(self) -> None:
        self._state.racks = [
            RackReading(
                name=rack.name,
                description=rack.description,
                power_kw=None,
                warning_kw=rack.warning_kw,
                critical_kw=rack.critical_kw,
                status=RackStatus.UNKNOWN,
                pdus=[
                    PduReading(
                        name=pdu.name,
                        host=pdu.host,
                        power_kw=None,
                        energy_kwh=None,
                        status=PduStatus.UNREACHABLE,
                        last_poll=None,
                    )
                    for pdu in rack.pdus
                ],
            )
            for rack in self._config.racks
        ]

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="rack-power-monitor-poller")

    async def stop(self) -> None:
        if self._stop:
            self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._stop = None

    async def poll_now(self) -> DashboardState:
        await self._poll_once()
        return self.get_state()

    async def _run_loop(self) -> None:
        while self._stop and not self._stop.is_set():
            await self._poll_once()
            interval = self.config.poll_interval_seconds
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                continue

    async def _poll_once(self) -> None:
        config = self.config
        now = datetime.now(timezone.utc)

        try:
            rack_results: list[tuple[RackConfig, list[PduReading]]] = []
            for rack in config.racks:
                tasks = [self._read_pdu(pdu, config, now) for pdu in rack.pdus]
                pdu_readings = list(await asyncio.gather(*tasks))
                rack_results.append((rack, pdu_readings))
        except Exception:
            logger.exception("SNMP poll failed")
            return

        rack_readings = [
            self._aggregate_rack(rack, pdu_readings) for rack, pdu_readings in rack_results
        ]

        notifier = AlertNotifier(config.smtp, config.webhooks)
        self._alert_tracker.process(rack_readings, notifier)

        with self._lock:
            self._state.racks = rack_readings
            self._state.last_poll = now
            for rack in rack_readings:
                self._history.add(rack.name, rack.power_kw, now)

    async def _read_pdu(self, pdu: PduConfig, config: AppConfig, now: datetime) -> PduReading:
        pdu_id = f"{pdu.host}:{pdu.name}"
        power_result, energy_result = await poll_pdu_power_energy(
            pdu.host, pdu.community, config.snmp
        )

        if not power_result.success:
            prev = self._last_pdu_readings.get(pdu_id)
            if prev and prev.power_kw is not None:
                return PduReading(
                    name=pdu.name,
                    host=pdu.host,
                    power_kw=prev.power_kw,
                    energy_kwh=prev.energy_kwh,
                    status=PduStatus.STALE,
                    last_poll=prev.last_poll,
                    error=power_result.error,
                )
            return PduReading(
                name=pdu.name,
                host=pdu.host,
                power_kw=None,
                energy_kwh=None,
                status=PduStatus.UNREACHABLE,
                last_poll=None,
                error=power_result.error,
            )

        power_kw = power_result.value / config.snmp.power_divisor if power_result.value is not None else None
        energy_kwh = None
        if energy_result.success and energy_result.value is not None:
            energy_kwh = energy_result.value / config.snmp.energy_divisor

        reading = PduReading(
            name=pdu.name,
            host=pdu.host,
            power_kw=power_kw,
            energy_kwh=energy_kwh,
            status=PduStatus.OK,
            last_poll=now,
            error=None,
        )
        self._last_pdu_readings[pdu_id] = reading
        return reading

    def _aggregate_rack(self, rack: RackConfig, pdus: list[PduReading]) -> RackReading:
        reachable = [p for p in pdus if p.status != PduStatus.UNREACHABLE]
        if not reachable:
            return RackReading(
                name=rack.name,
                description=rack.description,
                power_kw=None,
                warning_kw=rack.warning_kw,
                critical_kw=rack.critical_kw,
                status=RackStatus.UNKNOWN,
                pdus=pdus,
            )

        total_kw = sum(p.power_kw or 0 for p in reachable)
        has_stale = any(p.status == PduStatus.STALE for p in pdus)

        if total_kw >= rack.critical_kw:
            status = RackStatus.CRITICAL
        elif total_kw >= rack.warning_kw:
            status = RackStatus.WARNING
        else:
            status = RackStatus.OK

        if has_stale and status == RackStatus.OK:
            status = RackStatus.WARNING

        headroom = rack.critical_kw - total_kw
        percent = (total_kw / rack.critical_kw * 100) if rack.critical_kw else None

        return RackReading(
            name=rack.name,
            description=rack.description,
            power_kw=round(total_kw, 2),
            warning_kw=rack.warning_kw,
            critical_kw=rack.critical_kw,
            status=status,
            pdus=pdus,
            headroom_kw=round(headroom, 2),
            percent_of_limit=round(percent, 1) if percent is not None else None,
        )
