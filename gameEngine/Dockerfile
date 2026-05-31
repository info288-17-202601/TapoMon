# ──────────────────────────────────────────────────────
#  gameEngine/Dockerfile
#  Build context: ./gameEngine
#
#  Interactive console app — always run with:
#    docker run -it tapomon-client
#  or via docker-compose.client.yml (which sets stdin_open + tty).
# ──────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full game engine source
COPY . .

# Port used when this client acts as P2P battle HOST.
# Publish only when hosting: docker run -it -p 55201:55201 tapomon-client
# (handled by docker-compose.client.yml via the P2P_HOST profile)
EXPOSE 55201

CMD ["python", "main.py"]
