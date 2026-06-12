FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY rack_power_monitor/ rack_power_monitor/
COPY templates/ templates/
COPY static/ static/
COPY config.example.yaml ./

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir .

ENV RACK_POWER_MONITOR_CONFIG=/app/config.yaml

EXPOSE 8080

CMD ["python", "-m", "rack_power_monitor.main"]
