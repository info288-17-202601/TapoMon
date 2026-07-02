# ──────────────────────────────────────────────────────
#  server/coordinator/Dockerfile
#  Build context: ./server  (igual que el servidor regional)
#
#  El coordinador usa los mismos imports "from server.coordinator.X import ..."
#  así que comparte el build context con el servidor, pero ejecuta
#  un módulo diferente (server.coordinator.main).
# ──────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire server package into /app/server/
# so that "from server.coordinator.X import ..." works from /app
COPY . /app/server/

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server.coordinator.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
