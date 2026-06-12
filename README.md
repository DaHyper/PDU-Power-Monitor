# Rack Power Monitor

Per-rack power monitoring for APC PDUs. Combines **kW draw** across multiple PDUs via SNMP and alerts before you hit your colo power cap.

## Features

- **SNMP polling** of APC AP8841 PDUs (rPDU2 MIB, SNMP v2c)
- **Per-rack aggregation** — sums power from configured PDUs per rack
- **Web dashboard** with OK / Warning / Danger states and per-PDU breakdown
- **Configuration UI** for PDUs, thresholds, poll interval, and SMTP alerts
- **Email alerts** with cooldown (warning, critical, PDU unreachable, recovery)
- **Stale/unreachable PDUs** are clearly flagged — never silently shown as zero
- Single **YAML config file** — no hardcoded IPs or credentials

## Quick start

### 1. Copy and edit config

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your PDU IPs, community strings, racks, and SMTP settings
```

### 2. Verify SNMP OIDs (important)

APC firmware returns power in scaled integer units. Confirm with a live walk:

```bash
snmpwalk -v2c -c public 10.0.1.11 1.3.6.1.4.1.318.1.1.26.4.3.1.5
```

Adjust `snmp.power_divisor` in config until the dashboard matches your expected kW reading. Common values:

| Raw SNMP value | Divisor | Result |
|----------------|---------|--------|
| 1410 (watts)   | 1000    | 1.41 kW |
| 14100 (tenths of W) | 10000 | 1.41 kW |

### 3. Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
rack-power-monitor
# or: python -m rack-power-monitor.main
```

Open http://localhost:8080 for the dashboard and http://localhost:8080/config for settings.

### 4. Docker

```bash
cp config.example.yaml config.yaml
# edit config.yaml
docker build -t rack-power-monitor .
docker run -d -p 8080:8080 -v $(pwd)/config.yaml:/app/config.yaml rack-power-monitor
```

## Configuration

All settings live in `config.yaml`:

| Section | Purpose |
|---------|---------|
| `poll_interval_seconds` | How often to poll PDUs (30–60s typical) |
| `alert_cooldown_minutes` | Minimum time between repeat alert emails |
| `snmp` | OIDs, timeout, power scaling divisor |
| `racks` | Rack name, location, thresholds, PDU list |
| `smtp` | Host, port, TLS, auth, recipients |

### Threshold logic (kW draw)

Per rack, combined instantaneous power from all reachable PDUs:

- **OK** (green): below warning threshold (default 2.5 kW)
- **Warning** (yellow): at or above warning threshold
- **Danger** (red): at or above critical threshold (default 3.0 kW)

> **Note:** Colo caps are almost always **kW** (instantaneous draw), not kWh (energy over time). Rack Power Monitor tracks kW draw. Energy OID is polled for display but not used for threshold alerts in v1.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Current rack/PDU readings |
| POST | `/api/refresh` | Force immediate poll |
| GET/PUT | `/api/config` | Read/save configuration |
| POST | `/api/test/pdu` | Test single PDU SNMP |
| POST | `/api/test/pdu/all` | Test all configured PDUs |
| POST | `/api/test/smtp` | Send test alert email |

## Project structure

```
rack-power-monitor/           Python package (SNMP, polling, alerts, API)
templates/          Dashboard and config HTML
static/             CSS and JavaScript
config.example.yaml Example configuration
Dockerfile          Container build
```

## License

MIT
