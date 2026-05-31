# ──────────────────────────────────────────────────────
#  server/Dockerfile
#  Build context: ./server  (only the server package)
#
#  The server package uses absolute imports: "from server.X import ..."
#  so the COPY lands under /app/server/ and WORKDIR stays at /app.
# ──────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire server package into /app/server/
# so that "from server.X import ..." works from /app
COPY . /app/server/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
