# 🐾 TapoMon

> Mascotas virtuales con combate P2P en red local, sincronización con servidor central y simulación autónoma por independencia.

---

## Tabla de contenidos

- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Especificación de Despliegue](#especificación-de-despliegue)
  - [Despliegue del Servidor](#despliegue-del-servidor)
  - [Despliegue del Cliente](#despliegue-del-cliente)
  - [Variables de entorno](#variables-de-entorno)
- [Combate P2P](#combate-p2p)
- [Varios jugadores en la misma máquina](#varios-jugadores-en-la-misma-máquina)
- [Desarrollo sin Docker](#desarrollo-sin-docker)
- [Tests](#tests)
- [Mecánica de Independencia](#mecánica-de-independencia)
- [Estructura del proyecto](#estructura-del-proyecto)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  Servidor central  (docker-compose.yml)                     │
│                                                             │
│  ┌───────────────┐    ┌──────────────────────────────────┐  │
│  │   mongodb     │◄───│  server  (FastAPI + APScheduler) │  │
│  │  (interno)    │    │  puerto 8000                     │  │
│  └───────────────┘    └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
            ▲ HTTP (registro, login, sync)
            │
┌───────────┴─────────────┐   ┌────────────────────────────────┐
│  Cliente — Jugador A    │   │  Cliente — Jugador B           │
│  (docker-compose.client)│   │  (docker-compose.client)       │
│                         │   │                                │
│  ┌────────────────────┐ │   │ ┌────────────────────────────┐ │
│  │ mongodb-local (A)  │ │   │ │ mongodb-local (B)          │ │
│  │  save data de A    │ │   │ │  save data de B            │ │
│  └────────────────────┘ │   │ └────────────────────────────┘ │
│  ┌────────────────────┐ │   │ ┌────────────────────────────┐ │
│  │   gameEngine       │◄────►│   gameEngine               │ │
│  │   puerto 55201     │ │   │ │   puerto 55201/55202       │ │
│  └────────────────────┘ │   │ └────────────────────────────┘ │
└─────────────────────────┘   └────────────────────────────────┘
         P2P TCP directo entre jugadores (combate)
```

**Reglas clave:**
- El servidor se levanta **una sola vez** y es compartido por todos los jugadores.
- Cada jugador tiene su **propio contenedor** con su propia base de datos local.
- Los combates P2P se conectan **directamente** entre clientes (sin pasar por el servidor).

---

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2 (incluido en Docker Desktop)

No se necesita Python, MongoDB ni ninguna dependencia instalada localmente.

> En caso de usar windows hay que usar wsl2 y tener la wsl integration activada en docker desktop además de seguir los siguientes comandos:
>
> En powershell:
>
>```bash
>wsl --set-default-version 2
>wsl --set-version Ubuntu 2   
>wsl --update
>```
>En ubuntu(WSL2):
>
>```bash
>sudo apt update
>sudo apt install x11-xserver-utils
>```

> En caso de usar linux no es necesario hacer nada de lo anterior, pero puede ser necesario instalar xorg-xhost en caso de intentar ejecutar en un entorno que no sea x11 (Por ejemplo wayland o hyprland).
>
> En arch linux:
> ```bash
> sudo pacman -S xorg-xhost
> ```

---

## Especificación de Despliegue

A continuación se detalla la especificación para levantar tanto la infraestructura central como los clientes de los jugadores usando contenedores, además del detalle de sus variables de entorno.

### Despliegue del Servidor

```bash
# Clonar el repositorio
git clone https://github.com/info288-17-202601/TapoMon.git
cd TapoMon

# Levantar el servidor central y su base de datos
docker compose up -d

# Verificar que está corriendo
curl http://localhost:8000/
# → {"status": "ok", "service": "TapoMon Central Server"}

# Ver logs en tiempo real
docker compose logs -f server

# Apagar el servidor
docker compose down
```

El servidor queda disponible en `http://localhost:8000`.
La documentación interactiva de la API está en `http://localhost:8000/docs`.

> **Nota:** Los datos de MongoDB del servidor se guardan en el volumen Docker
> `tapomon-server-mongo` y persisten entre reinicios.

---

### Despliegue del Cliente

Cada jugador ejecuta **su propio stack** usando un nombre de proyecto único (`-p`).
Esto garantiza que cada jugador tenga su propia base de datos local aislada.

```bash
# Construir la imagen del cliente (solo la primera vez o tras cambios)
docker compose -f docker-compose.client.yml build

# Ejecuta el script interactivo (reemplace "ben" con su nombre)
./play.sh ben
```

> **Si el servidor se ejecuta en otra máquina**, indique su dirección antes de correr el script:
> ```bash
> TAPOMON_SERVER_URL=http://192.168.1.10:8000 ./play.sh ben
> ```

### Parar y eliminar el cliente

```bash
# Parar el cliente (los datos se conservan)
docker compose -f docker-compose.client.yml -p ben down

# Parar el cliente Y BORRAR todos los datos guardados (save data)
docker compose -f docker-compose.client.yml -p ben down -v
```

---

## Combate P2P

Los combates suceden directamente entre dos jugadores sin intermediario.
Todo ocurre desde el menú del juego sin reiniciar nada.

### Paso 1 — El jugador HOST

El jugador que desea **recibir** el reto selecciona en el menú:
```
⚔️  COMBATE P2P → 1. Ser HOST
```

El juego mostrará:
```
📡 Tu IP:    192.168.1.50
🔌 Puerto:   55201

Comparta estos datos con su rival para que se conecte.
```

> **Importante:** Para que el juego muestre su IP real de red (y no la IP interna del contenedor),
> pase su IP al levantar el cliente:
> ```bash
> P2P_HOST_IP=192.168.1.50 ./play.sh ben
> ```
> Puede encontrar su IP utilizando el comando `ip addr` o `hostname -I`.

### Paso 2 — El jugador CHALLENGER

El jugador que desea **retar** selecciona en el menú:
```
⚔️  COMBATE P2P → 2. Unirse
```
e introduce la IP y puerto que compartió el host.

### El combate

El sistema de turnos, tiradas de dados y cálculo de daño se ejecutan localmente
entre los dos clientes. Al terminar, cada jugador ve el resultado en su consola.

---

## Varios jugadores en la misma máquina

Si dos jugadores quieren probar en la **misma máquina**, deben usar puertos distintos
para el combate P2P y nombres de proyecto distintos:

```bash
# Jugador A — usa el puerto por defecto
P2P_HOST_IP=host.docker.internal P2P_PORT=55201 ./play.sh renton

# Jugador B — usa un puerto diferente (en otra terminal)
P2P_HOST_IP=host.docker.internal P2P_PORT=55202 ./play.sh pascal
```

Cuando B rete a A, introducirá `host.docker.internal:55201` como IP y puerto.

---

### Variables de entorno

### Servidor (`docker-compose.yml`)

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb:27017` | Conexión a MongoDB |
| `MONGO_DB` | `Tapomon` | Nombre de la base de datos |
| `JWT_SECRET` | *(ver compose)* | Secreto para tokens JWT — **cambiar en producción** |
| `JWT_EXPIRATION_HOURS` | `24` | Duración del token de sesión |
| `IDLE_TICK_INTERVAL` | `60` | Segundos entre ticks de simulación IDLE |
| `INDEPENDENCIA_GROWTH` | `1` | Puntos de independencia ganados por tick saludable |
| `INDEPENDENCIA_HEALTH_THRESHOLD` | `60` | Salud mínima para ganar independencia |

### Cliente (`docker-compose.client.yml`)

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `MONGO_URI` | `mongodb://mongodb-local:27017` | MongoDB local del jugador (no cambiar) |
| `MONGO_DB` | `Tapomon` | Nombre de la base de datos local |
| `TAPOMON_SERVER_URL` | `http://host.docker.internal:8000` | URL del servidor central |
| `TAPOMON_REQUEST_TIMEOUT` | `10` | Timeout HTTP en segundos |
| `P2P_HOST_IP` | *(auto-detect)* | IP a mostrar cuando el jugador es HOST |
| `P2P_PORT` | `55201` | Puerto del host para el mapeo Docker |

---

## Desarrollo sin Docker

Si desea ejecutar el proyecto directamente en su máquina (sin contenedores):

### Servidor

```bash
cd TapoMon

# Crear entorno virtual
python3 -m venv server/.venv
source server/.venv/bin/activate

# Instalar dependencias
pip install -r server/requirements.txt

# Asegurarse de que MongoDB esté ejecutándose
sudo systemctl start mongod

# Levantar el servidor
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### Cliente

```bash
cd TapoMon/gameEngine

# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el juego
python main.py
```

---

## Tests

Los tests del servidor se ejecutan con `pytest` usando el entorno virtual del servidor:

```bash
cd TapoMon

# Todos los tests
server/.venv/bin/python -m pytest server/tests/ -v

# Solo los tests de la mecánica de Independencia
server/.venv/bin/python -m pytest server/tests/test_independencia.py -v

# Solo los tests del motor IDLE
server/.venv/bin/python -m pytest server/tests/test_idle_engine.py -v
```

Los tests unitarios (idle engine, independencia) **no requieren MongoDB**.
Los tests de integración sí requieren MongoDB corriendo.

---

## Mecánica de Independencia

Cuando un Tapo está en modo IDLE (jugador desconectado), el servidor simula
su comportamiento autónomo según su stat `independencia`:

| `independencia` | Probabilidad de actuar por tick |
|---|---|
| 0 | 0 % — nunca actúa solo |
| 50 | 50 % — actúa en la mitad de los ticks |
| 100 | 100 % — actúa en casi todos los ticks |

**Acciones autónomas posibles por tick:**

| Acción | Probabilidad | Efecto |
|---|---|---|
| Comer solo | 40 % | `hambre +25` |
| Jugar solo | 30 % | `felicidad +20`, `energía −10` |
| Entrenar stat aleatorio | 30 % | `fuerza/defensa/velocidad +1`, `energía −10` |

**Crecimiento:** La independencia crece `+1` por tick mientras `salud ≥ 60`.
Un Tapo descuidado (salud baja) no se vuelve más independiente.

Al reconectarse, el jugador recibe un mensaje en su bandeja con un resumen
de lo que hizo su Tapo mientras estaba solo.

---

## Estructura del proyecto

```
TapoMon/
├── docker-compose.yml          # Stack del servidor (mongodb + server)
├── docker-compose.client.yml   # Stack del cliente (mongodb-local + gameEngine)
├── pytest.ini                  # Configuración de pytest
│
├── server/                     # Servidor central FastAPI
│   ├── Dockerfile
│   ├── .env.example
│   ├── requirements.txt
│   ├── main.py                 # Punto de entrada + APScheduler
│   ├── config.py               # Configuración centralizada
│   ├── api/
│   │   ├── auth_routes.py      # POST /auth/login, /auth/register
│   │   ├── sync_routes.py      # POST /sync/upload, GET /sync/resume/{id}
│   │   └── dashboard_routes.py
│   ├── services/
│   │   ├── auth_service.py     # Lógica de autenticación y registro
│   │   ├── idle_engine.py      # Simulación IDLE + mecánica de independencia
│   │   └── sync_service.py     # Upload/resume del estado del Tapo
│   ├── models/
│   │   └── schemas.py          # Esquemas Pydantic (request/response)
│   ├── db/
│   │   └── mongo.py            # Conexión MongoDB del servidor
│   ├── templates/              # Dashboard web
│   └── tests/                  # Tests unitarios e integración
│
└── gameEngine/                 # Cliente (consola interactiva)
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                 # Punto de entrada + menú principal
    ├── engine/
    │   └── game_engine.py      # Lógica de acciones, IDLE, estadísticas
    ├── network/
    │   ├── sync_client.py      # HTTP hacia el servidor (login, register, sync)
    │   └── config.py           # URL del servidor, timeouts
    ├── p2pEngine/
    │   ├── p2p_server.py       # Host del combate (TCP 55201)
    │   ├── p2p_client.py       # Challenger del combate
    │   ├── combat_engine.py    # Reglas de combate (D20, daño, tipos)
    │   ├── p2p_protocol.py     # Protocolo de mensajes JSON sobre TCP
    │   └── battle_cli.py       # Interfaz de consola para combates
    ├── models/
    │   └── tapo.py             # Modelo de datos del Tapo
    └── db/
        ├── connection.py       # Conexión MongoDB local del jugador
        └── local_db.py         # Operaciones CRUD locales
```
