from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PduConfig:
    name: str
    host: str
    community: str = "public"


@dataclass
class RackConfig:
    name: str
    location: str
    warning_kw: float
    critical_kw: float
    pdus: list[PduConfig] = field(default_factory=list)


@dataclass
class SnmpConfig:
    version: str = "2c"
    timeout_seconds: int = 5
    retries: int = 2
    power_oid: str = "1.3.6.1.4.1.318.1.1.26.4.3.1.5"
    power_divisor: float = 10000.0
    energy_oid: str = "1.3.6.1.4.1.318.1.1.26.4.3.1.9"
    energy_divisor: float = 10.0


@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    security: str = "tls"
    username: str = ""
    password: str = ""
    from_address: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    config_path: str = "config.yaml"


@dataclass
class AppConfig:
    poll_interval_seconds: int = 60
    alert_cooldown_minutes: int = 15
    snmp: SnmpConfig = field(default_factory=SnmpConfig)
    racks: list[RackConfig] = field(default_factory=list)
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


def _parse_pdu(data: dict[str, Any]) -> PduConfig:
    return PduConfig(
        name=data["name"],
        host=data["host"],
        community=data.get("community", "public"),
    )


def _parse_rack(data: dict[str, Any]) -> RackConfig:
    return RackConfig(
        name=data["name"],
        location=data.get("location", ""),
        warning_kw=float(data.get("warning_kw", 2.5)),
        critical_kw=float(data.get("critical_kw", 3.0)),
        pdus=[_parse_pdu(p) for p in data.get("pdus", [])],
    )


def _parse_snmp(data: dict[str, Any] | None) -> SnmpConfig:
    data = data or {}
    return SnmpConfig(
        version=data.get("version", "2c"),
        timeout_seconds=int(data.get("timeout_seconds", 5)),
        retries=int(data.get("retries", 2)),
        power_oid=data.get("power_oid", "1.3.6.1.4.1.318.1.1.26.4.3.1.5"),
        power_divisor=float(data.get("power_divisor", 10000)),
        energy_oid=data.get("energy_oid", "1.3.6.1.4.1.318.1.1.26.4.3.1.9"),
        energy_divisor=float(data.get("energy_divisor", 10)),
    )


def _parse_smtp(data: dict[str, Any] | None) -> SmtpConfig:
    data = data or {}
    recipients = data.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]
    return SmtpConfig(
        host=data.get("host", ""),
        port=int(data.get("port", 587)),
        security=data.get("security", "tls"),
        username=data.get("username", ""),
        password=data.get("password", ""),
        from_address=data.get("from_address", ""),
        recipients=list(recipients),
    )


def _parse_server(data: dict[str, Any] | None) -> ServerConfig:
    data = data or {}
    return ServerConfig(
        host=data.get("host", "0.0.0.0"),
        port=int(data.get("port", 8080)),
        config_path=data.get("config_path", "config.yaml"),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    return AppConfig(
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
        alert_cooldown_minutes=int(raw.get("alert_cooldown_minutes", 15)),
        snmp=_parse_snmp(raw.get("snmp")),
        racks=[_parse_rack(r) for r in raw.get("racks", [])],
        smtp=_parse_smtp(raw.get("smtp")),
        server=_parse_server(raw.get("server")),
    )


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "poll_interval_seconds": config.poll_interval_seconds,
        "alert_cooldown_minutes": config.alert_cooldown_minutes,
        "snmp": {
            "version": config.snmp.version,
            "timeout_seconds": config.snmp.timeout_seconds,
            "retries": config.snmp.retries,
            "power_oid": config.snmp.power_oid,
            "power_divisor": config.snmp.power_divisor,
            "energy_oid": config.snmp.energy_oid,
            "energy_divisor": config.snmp.energy_divisor,
        },
        "racks": [
            {
                "name": rack.name,
                "location": rack.location,
                "warning_kw": rack.warning_kw,
                "critical_kw": rack.critical_kw,
                "pdus": [
                    {
                        "name": pdu.name,
                        "host": pdu.host,
                        "community": pdu.community,
                    }
                    for pdu in rack.pdus
                ],
            }
            for rack in config.racks
        ],
        "smtp": {
            "host": config.smtp.host,
            "port": config.smtp.port,
            "security": config.smtp.security,
            "username": config.smtp.username,
            "password": config.smtp.password,
            "from_address": config.smtp.from_address,
            "recipients": list(config.smtp.recipients),
        },
        "server": {
            "host": config.server.host,
            "port": config.server.port,
            "config_path": config.server.config_path,
        },
    }


def save_config(path: str | Path, data: dict[str, Any]) -> AppConfig:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
    return load_config(config_path)


def merge_config_update(current: AppConfig, update: dict[str, Any]) -> dict[str, Any]:
    merged = config_to_dict(current)
    deep = copy.deepcopy(update)

    for key in ("poll_interval_seconds", "alert_cooldown_minutes"):
        if key in deep:
            merged[key] = deep[key]

    if "snmp" in deep:
        merged["snmp"].update(deep["snmp"])

    if "racks" in deep:
        merged["racks"] = deep["racks"]

    if "smtp" in deep:
        smtp_update = deep["smtp"]
        if "password" in smtp_update and smtp_update["password"] in ("", "********"):
            smtp_update.pop("password", None)
        merged["smtp"].update(smtp_update)

    if "server" in deep:
        merged["server"].update(deep["server"])

    return merged
