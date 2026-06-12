# Rack Power Monitor — Mac setup guide

Step-by-step instructions to run Rack Power Monitor on macOS.

---

## What you need first

| Requirement | Notes |
|-------------|--------|
| **macOS** | Any recent version (Ventura, Sonoma, Sequoia, etc.) |
| **Python 3.11+** | Check with `python3 --version` |
| **Network access to your PDUs** | Your Mac must reach the PDU IPs on UDP port 161 (SNMP) |
| **PDU details** | IP address and SNMP v2c community string for each APC AP8841 |

Optional but recommended:

```bash
brew install net-snmp
```

This gives you `snmpwalk` / `snmpget` so you can verify SNMP before starting the app.

---

## Step 1 — Open the project folder

If you already cloned the repo:

```bash
cd ~/Documents/GitHub/PDU-Power-Monitor
```

If you haven't cloned it yet:

```bash
cd ~/Documents/GitHub
git clone <your-repo-url> PDU-Power-Monitor
cd PDU-Power-Monitor
```

---

## Step 2 — Check Python

```bash
python3 --version
```

You should see **3.11** or newer. If Python is missing or too old:

```bash
brew install python@3.12
```

---

## Step 3 — Create a virtual environment

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your shell prompt should show `(.venv)`. You need to run `source .venv/bin/activate` again each time you open a new terminal tab.

---

## Step 4 — Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Optional — install the CLI entry point so you can run `rack-power-monitor` directly:

```bash
pip install -e .
```

---

## Step 5 — Create your config file

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your real values. At minimum, update:

1. **PDU IPs and community strings** under `racks` → `pdus`
2. **Rack names / locations** if you want
3. **SMTP settings** if you want email alerts (can skip for initial testing)

Example snippet:

```yaml
racks:
  - name: "Rack A"
    location: "Row 1 · Slots 1-2"
    warning_kw: 2.5
    critical_kw: 3.0
    pdus:
      - name: "PDU A1"
        host: "10.0.1.11"      # ← your PDU IP
        community: "public"    # ← your SNMP community
      - name: "PDU A2"
        host: "10.0.1.12"
        community: "public"
```

> `config.yaml` is git-ignored — it won't be committed. Keep SNMP communities and SMTP passwords here only.

You can also edit most settings later in the web UI at http://localhost:8080/config.

---

## Step 6 — Verify SNMP (strongly recommended)

Before starting the app, confirm your Mac can talk to a PDU:

```bash
snmpwalk -v2c -c public 10.0.1.11 1.3.6.1.4.1.318.1.1.26.4.3.1.5
```

Replace `public` and `10.0.1.11` with your community string and PDU IP.

You should get a numeric value back. Use it to set `snmp.power_divisor` in `config.yaml`:

| If raw value looks like… | Set `power_divisor` to… | Example |
|--------------------------|-------------------------|---------|
| Watts (e.g. `1410`) | `1000` | 1410 → 1.41 kW |
| Tenths of watts (e.g. `14100`) | `10000` | 14100 → 1.41 kW |

If `snmpwalk` times out, fix network/firewall/VPN access before continuing — the app will show PDUs as unreachable too.

---

## Step 7 — Start the app

Make sure the virtual environment is active (`source .venv/bin/activate`), then:

```bash
python -m rack_power_monitor.main
```

Or, if you ran `pip install -e .` in Step 4:

```bash
rack-power-monitor
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8080
```

Leave this terminal window open while the app is running. Press **Ctrl+C** to stop it.

---

## Step 8 — Open the dashboard

In your browser:

| Page | URL |
|------|-----|
| **Dashboard** | http://localhost:8080 |
| **Configuration** | http://localhost:8080/config |

On the config page, use **Test all connections** to verify each PDU. Use **Save configuration** after making changes.

---

## Quick reference — every time you start it

```bash
cd ~/Documents/GitHub/PDU-Power-Monitor
source .venv/bin/activate
python -m rack_power_monitor.main
```

Then open http://localhost:8080

---

## Troubleshooting

### `python3: command not found`

Install Python:

```bash
brew install python@3.12
```

### `Address already in use` (port 8080)

Something else is using port 8080. Either stop it:

```bash
lsof -ti:8080 | xargs kill
```

Or change the port in `config.yaml`:

```yaml
server:
  port: 8081
```

Then open http://localhost:8081

### PDUs show as unreachable on the dashboard

- Confirm you can `ping` the PDU IP from your Mac
- Confirm `snmpwalk` works (Step 6)
- Check the community string in `config.yaml`
- Make sure UDP 161 isn't blocked by a firewall or VPN

### Dashboard loads but power readings look wrong

Adjust `snmp.power_divisor` in `config.yaml` (or the config UI) until values match what you expect. Re-run the `snmpwalk` from Step 6 and do the math manually.

### Email alerts not sending

1. Fill in all `smtp:` fields in `config.yaml`
2. Go to http://localhost:8080/config
3. Click **Save configuration**, then **Send test email**

---

## Optional — run with Docker on Mac

If you prefer Docker instead of a local Python venv:

```bash
cp config.example.yaml config.yaml
# edit config.yaml first

docker build -t rack-power-monitor .
docker run -d -p 8080:8080 -v "$(pwd)/config.yaml:/app/config.yaml" rack-power-monitor
```

Open http://localhost:8080

---

## Next steps

- Tune warning/critical thresholds per rack in the config UI
- Add SMTP recipients for ops alerts
- Deploy to a small VM or container next to your LibreNMS box for 24/7 monitoring
