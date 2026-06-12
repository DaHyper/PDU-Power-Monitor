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
    snmp_version: str | None = None  # override global: 1 | 2c | 3


@dataclass
class RackConfig:
    name: str
    description: str
    warning_kw: float
    critical_kw: float
    pdus: list[PduConfig] = field(default_factory=list)


@dataclass
class SnmpV3Config:
    username: str = ""
    auth_password: str = ""
    priv_password: str = ""
    auth_protocol: str = "SHA"  # MD5 | SHA | SHA224 | SHA256 | SHA384 | SHA512 | none
    priv_protocol: str = "AES"  # DES | AES | AES192 | AES256 | none
    security_level: str = "authPriv"  # noAuthNoPriv | authNoPriv | authPriv


@dataclass
class SnmpConfig:
    version: str = "2c"
    timeout_seconds: int = 5
    retries: int = 2
    power_oid: str = "1.3.6.1.4.1.318.1.1.26.4.3.1.5.1"
    power_divisor: float = 100.0
    energy_oid: str = "1.3.6.1.4.1.318.1.1.26.4.3.1.9.1"
    energy_divisor: float = 10.0
    v3: SnmpV3Config = field(default_factory=SnmpV3Config)


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
class WebhookConfig:
    name: str = ""
    url: str = ""
    format: str = "generic"
    enabled: bool = True


@dataclass
class MaintenanceConfig:
    enabled: bool = False
    silence_alerts: bool = True
    message: str = ""
    until: str = ""  # ISO8601 UTC, optional auto-expire


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
    webhooks: list[WebhookConfig] = field(default_factory=list)
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


def _parse_pdu(data: dict[str, Any]) -> PduConfig:
    version = data.get("snmp_version")
    return PduConfig(
        name=data["name"],
        host=data["host"],
        community=data.get("community", "public"),
        snmp_version=str(version) if version is not None else None,
    )


def _parse_rack(data: dict[str, Any]) -> RackConfig:
    return RackConfig(
        name=data["name"],
        description=data.get("description", data.get("location", "")),
        warning_kw=float(data.get("warning_kw", 2.5)),
        critical_kw=float(data.get("critical_kw", 3.0)),
        pdus=[_parse_pdu(p) for p in data.get("pdus", [])],
    )


def _parse_snmp_v3(data: dict[str, Any] | None) -> SnmpV3Config:
    data = data or {}
    return SnmpV3Config(
        username=data.get("username", ""),
        auth_password=data.get("auth_password", ""),
        priv_password=data.get("priv_password", ""),
        auth_protocol=data.get("auth_protocol", "SHA"),
        priv_protocol=data.get("priv_protocol", "AES"),
        security_level=data.get("security_level", "authPriv"),
    )


def _parse_snmp(data: dict[str, Any] | None) -> SnmpConfig:
    data = data or {}
    return SnmpConfig(
        version=str(data.get("version", "2c")),
        timeout_seconds=int(data.get("timeout_seconds", 5)),
        retries=int(data.get("retries", 2)),
        power_oid=data.get("power_oid", "1.3.6.1.4.1.318.1.1.26.4.3.1.5.1"),
        power_divisor=float(data.get("power_divisor", 100)),
        energy_oid=data.get("energy_oid", "1.3.6.1.4.1.318.1.1.26.4.3.1.9.1"),
        energy_divisor=float(data.get("energy_divisor", 10)),
        v3=_parse_snmp_v3(data.get("v3")),
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


def _parse_webhook(data: dict[str, Any]) -> WebhookConfig:
    return WebhookConfig(
        name=data.get("name", ""),
        url=data.get("url", ""),
        format=data.get("format", "generic"),
        enabled=bool(data.get("enabled", True)),
    )


def _parse_maintenance(data: dict[str, Any] | None) -> MaintenanceConfig:
    data = data or {}
    return MaintenanceConfig(
        enabled=bool(data.get("enabled", False)),
        silence_alerts=bool(data.get("silence_alerts", True)),
        message=data.get("message", ""),
        until=data.get("until") or "",
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
        webhooks=[_parse_webhook(w) for w in raw.get("webhooks", [])],
        maintenance=_parse_maintenance(raw.get("maintenance")),
        server=_parse_server(raw.get("server")),
    )


def config_to_dict(config: AppConfig, mask_secrets: bool = True) -> dict[str, Any]:
    smtp_password = config.smtp.password
    if mask_secrets and smtp_password:
        smtp_password = "********"
    v3_auth = config.snmp.v3.auth_password
    v3_priv = config.snmp.v3.priv_password
    if mask_secrets:
        if v3_auth:
            v3_auth = "********"
        if v3_priv:
            v3_priv = "********"

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
            "v3": {
                "username": config.snmp.v3.username,
                "auth_password": v3_auth,
                "priv_password": v3_priv,
                "auth_protocol": config.snmp.v3.auth_protocol,
                "priv_protocol": config.snmp.v3.priv_protocol,
                "security_level": config.snmp.v3.security_level,
            },
        },
        "racks": [
            {
                "name": rack.name,
                "description": rack.description,
                "warning_kw": rack.warning_kw,
                "critical_kw": rack.critical_kw,
                "pdus": [
                    {
                        "name": pdu.name,
                        "host": pdu.host,
                        "community": pdu.community,
                        **({"snmp_version": pdu.snmp_version} if pdu.snmp_version else {}),
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
            "password": smtp_password,
            "from_address": config.smtp.from_address,
            "recipients": list(config.smtp.recipients),
        },
        "webhooks": [
            {
                "name": wh.name,
                "url": wh.url,
                "format": wh.format,
                "enabled": wh.enabled,
            }
            for wh in config.webhooks
        ],
        "maintenance": {
            "enabled": config.maintenance.enabled,
            "silence_alerts": config.maintenance.silence_alerts,
            "message": config.maintenance.message,
            "until": config.maintenance.until or None,
        },
        "server": {
            "host": config.server.host,
            "port": config.server.port,
            "config_path": config.server.config_path,
        },
    }


def config_to_yaml(config: AppConfig, mask_secrets: bool = False) -> str:
    return yaml.safe_dump(
        config_to_dict(config, mask_secrets=mask_secrets),
        default_flow_style=False,
        sort_keys=False,
    )


def save_config(path: str | Path, data: dict[str, Any]) -> AppConfig:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
    return load_config(config_path)


def _mask_placeholder(value: str | None) -> bool:
    return value in (None, "", "********")


def merge_config_update(current: AppConfig, update: dict[str, Any]) -> dict[str, Any]:
    merged = config_to_dict(current, mask_secrets=False)
    deep = copy.deepcopy(update)

    for key in ("poll_interval_seconds", "alert_cooldown_minutes"):
        if key in deep:
            merged[key] = deep[key]

    if "snmp" in deep:
        snmp_update = deep["snmp"]
        if "v3" in snmp_update:
            v3_update = snmp_update["v3"]
            if _mask_placeholder(v3_update.get("auth_password")):
                v3_update.pop("auth_password", None)
            if _mask_placeholder(v3_update.get("priv_password")):
                v3_update.pop("priv_password", None)
            merged["snmp"].setdefault("v3", {}).update(v3_update)
            del snmp_update["v3"]
        merged["snmp"].update(snmp_update)

    if "racks" in deep:
        merged["racks"] = deep["racks"]

    if "smtp" in deep:
        smtp_update = deep["smtp"]
        if _mask_placeholder(smtp_update.get("password")):
            smtp_update.pop("password", None)
        merged["smtp"].update(smtp_update)

    if "webhooks" in deep:
        merged["webhooks"] = deep["webhooks"]

    if "maintenance" in deep:
        merged["maintenance"].update(deep["maintenance"])

    if "server" in deep:
        merged["server"].update(deep["server"])

    return merged
