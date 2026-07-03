#!/bin/bash

if [ -z "$1" ]; then
  echo "Uso: ./play.sh <nombre_jugador>"
  echo "Ejemplo: ./play.sh alice"
  exit 1
fi

PLAYER=$(echo "$1" | tr '[:upper:]' '[:lower:]')

echo "🎮 Levantando entorno para: $PLAYER..."

# 0. Aseguramos que la red compartida de Docker exista
docker network inspect tapomon-shared-net >/dev/null 2>&1 || docker network create tapomon-shared-net

# 1. Aseguramos que la imagen base esté construida con el código más reciente
docker compose -f docker-compose.client.yml build gameengine

xhost +local:docker > /dev/null 2>&1

echo "🎮 Entrando al juego..."
# 2. Ejecutamos el juego en modo interactivo, mapeando puertos para el P2P
# Al salir del juego, el contenedor efímero se destruye automáticamente (--rm)
docker compose -f docker-compose.client.yml -p "$PLAYER" run --rm --service-ports gameengine
