#!/bin/bash

if [ -z "$1" ]; then
  echo "Uso: ./play.sh <nombre_jugador>"
  echo "Ejemplo: ./play.sh alice"
  exit 1
fi

PLAYER=$1

echo "🎮 Levantando entorno para: $PLAYER..."

# 1. Aseguramos que la imagen base esté construida con el código más reciente
docker compose -f docker-compose.client.yml build gameengine

# 2. Aseguramos que la base de datos local de este jugador esté corriendo en background
docker compose -f docker-compose.client.yml -p "$PLAYER" up -d mongodb-local

echo "🎮 Entrando al juego..."
# 2. Ejecutamos el juego en modo interactivo, mapeando puertos para el P2P
# Al salir del juego, el contenedor efímero se destruye automáticamente (--rm)
docker compose -f docker-compose.client.yml -p "$PLAYER" run --rm --service-ports gameengine
