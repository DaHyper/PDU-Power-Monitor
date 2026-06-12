from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from pydantic import BaseModel

import yaml

from rack_power_monitor import __version__
from rack_power_monitor.alerts import AlertNotifier
from rack_power_monitor.config import (
    PduConfig,
    config_to_dict,
    config_to_yaml,
    load_config,
    merge_config_update,
    save_config,
)
from rack_power_monitor.poller import Poller
from rack_power_monitor.snmp_client import test_pdu_connection

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

DEFAULT_CONFIG = os.environ.get("RACK_POWER_MONITOR_CONFIG", str(BASE_DIR / "config.yaml"))


def _resolve_config_path() -> str:
    if Path(DEFAULT_CONFIG).exists():
        return DEFAULT_CONFIG
    example = BASE_DIR / "config.example.yaml"
    if example.exists():
        return str(example)
    return DEFAULT_CONFIG


config_path = _resolve_config_path()
poller = Poller(config_path)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await poller.start()
    yield
    await poller.stop()


app = FastAPI(title="Rack Power Monitor", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ConfigUpdate(BaseModel):
    poll_interval_seconds: int | None = None
    alert_cooldown_minutes: int | None = None
    snmp: dict | None = None
    racks: list[dict] | None = None
    smtp: dict | None = None
    webhooks: list[dict] | None = None
    maintenance: dict | None = None
    server: dict | None = None


class PduTestRequest(BaseModel):
    host: str
    community: str = "public"
    snmp_version: str | None = None


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"version": __version__},
    )


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "config.html",
        {"version": __version__},
    )


@app.get("/api/status")
async def api_status() -> JSONResponse:
    return JSONResponse(poller.get_state().to_dict())


@app.post("/api/refresh")
async def api_refresh() -> JSONResponse:
    state = await poller.poll_now()
    return JSONResponse(state.to_dict())


@app.get("/api/config")
async def api_get_config() -> JSONResponse:
    config = poller.config
    data = config_to_dict(config)
    if data["smtp"].get("password"):
        data["smtp"]["password"] = "********"
    return JSONResponse(data)


@app.put("/api/config")
async def api_save_config(body: ConfigUpdate) -> JSONResponse:
    try:
        update = body.model_dump(exclude_none=True)
        merged = merge_config_update(poller.config, update)
        save_config(config_path, merged)
        poller.reload_config()
        data = config_to_dict(poller.config)
        if data["smtp"].get("password"):
            data["smtp"]["password"] = "********"
        return JSONResponse({"ok": True, "config": data})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/config/export")
async def api_export_config() -> Response:
    yaml_text = config_to_yaml(poller.config, mask_secrets=False)
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": 'attachment; filename="rack-power-monitor-config.yaml"',
        },
    )


@app.post("/api/config/import")
async def api_import_config(file: UploadFile = File(...)) -> JSONResponse:
    try:
        raw = await file.read()
        data = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Config must be a YAML mapping")
        save_config(config_path, data)
        poller.reload_config()
        result = config_to_dict(poller.config, mask_secrets=True)
        if result["smtp"].get("password"):
            result["smtp"]["password"] = "********"
        return JSONResponse({"ok": True, "config": result})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/test/pdu")
async def api_test_pdu(body: PduTestRequest) -> JSONResponse:
    config = poller.config
    pdu = PduConfig(
        name="test",
        host=body.host,
        community=body.community,
        snmp_version=body.snmp_version,
    )
    result = await test_pdu_connection(pdu, config.snmp)
    if result.success and result.value is not None:
        power_kw = result.value / config.snmp.power_divisor
        return JSONResponse(
            {
                "ok": True,
                "raw_value": result.value,
                "power_kw": round(power_kw, 3),
            }
        )
    return JSONResponse({"ok": False, "error": result.error or "Unknown error"})


@app.post("/api/test/pdu/all")
async def api_test_all_pdus() -> JSONResponse:
    config = poller.config
    tasks = []
    meta = []
    for rack in config.racks:
        for pdu in rack.pdus:
            tasks.append(test_pdu_connection(pdu, config.snmp))
            meta.append((rack.name, pdu))
    snmp_results = await asyncio.gather(*tasks)

    results = []
    for (rack_name, pdu), result in zip(meta, snmp_results, strict=True):
        entry = {
            "rack": rack_name,
            "name": pdu.name,
            "host": pdu.host,
            "ok": result.success,
            "error": result.error,
        }
        if result.success and result.value is not None:
            entry["raw_value"] = result.value
            entry["power_kw"] = round(result.value / config.snmp.power_divisor, 3)
        results.append(entry)
    return JSONResponse({"results": results})


@app.post("/api/test/smtp")
async def api_test_smtp() -> JSONResponse:
    notifier = AlertNotifier(poller.config.smtp, poller.config.webhooks)
    if not notifier.email.configured:
        raise HTTPException(status_code=400, detail="SMTP not configured")
    try:
        notifier.send_test_email()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse({"ok": True})


@app.post("/api/test/webhooks")
async def api_test_webhooks() -> JSONResponse:
    notifier = AlertNotifier(poller.config.smtp, poller.config.webhooks)
    if not notifier.webhooks.configured:
        raise HTTPException(status_code=400, detail="No webhooks configured")
    try:
        notifier.send_test_webhooks()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse({"ok": True})


def main() -> None:
    cfg_path = _resolve_config_path()
    try:
        config = load_config(cfg_path)
    except FileNotFoundError:
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        print("Copy config.example.yaml to config.yaml and edit it.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load config ({cfg_path}): {exc}", file=sys.stderr)
        sys.exit(1)

    import uvicorn

    print(f"Rack Power Monitor starting on http://{config.server.host}:{config.server.port}")
    print(f"Config: {cfg_path}")

    try:
        uvicorn.run(
            "rack_power_monitor.main:app",
            host=config.server.host,
            port=config.server.port,
            reload=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Server failed to start: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
