FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY rackwatt/ rackwatt/
COPY templates/ templates/
COPY static/ static/
COPY config.example.yaml ./

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir .

ENV RACKWATT_CONFIG=/app/config.yaml

EXPOSE 8080

CMD ["python", "-m", "rackwatt.main"]
