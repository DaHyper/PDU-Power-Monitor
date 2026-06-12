from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from rackwatt.config import SnmpConfig

_engine = SnmpEngine()


@dataclass
class SnmpResult:
    success: bool
    value: float | None = None
    error: str | None = None


def _normalize_oid(oid: str) -> str:
    return oid.lstrip(".")


async def snmp_get(host: str, community: str, oid: str, snmp: SnmpConfig) -> SnmpResult:
    oid = _normalize_oid(oid)
    try:
        transport = await UdpTransportTarget.create(
            (host, 161),
            timeout=snmp.timeout_seconds,
            retries=snmp.retries,
        )
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            _engine,
            CommunityData(community, mpModel=1 if snmp.version == "2c" else 0),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
    except Exception as exc:  # noqa: BLE001
        return SnmpResult(success=False, error=str(exc))

    if error_indication:
        return SnmpResult(success=False, error=str(error_indication))
    if error_status:
        return SnmpResult(success=False, error=str(error_status.prettyPrint()))

    for _name, val in var_binds:
        try:
            numeric = float(val)
        except (TypeError, ValueError):
            return SnmpResult(success=False, error=f"Non-numeric SNMP value: {val!r}")
        return SnmpResult(success=True, value=numeric)

    return SnmpResult(success=False, error="Empty SNMP response")


async def poll_pdu_power_energy(
    host: str,
    community: str,
    snmp: SnmpConfig,
) -> tuple[SnmpResult, SnmpResult]:
    power_task = snmp_get(host, community, snmp.power_oid, snmp)
    energy_task = snmp_get(host, community, snmp.energy_oid, snmp)
    return await asyncio.gather(power_task, energy_task)


def test_pdu_connection(host: str, community: str, snmp: SnmpConfig) -> SnmpResult:
    return asyncio.run(snmp_get(host, community, snmp.power_oid, snmp))
