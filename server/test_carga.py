"""Script de prueba para generar múltiples peticiones concurrentes al servidor.

Usa el endpoint /debug/worker-info para ver qué PID y CPU responde cada petición.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import urllib.error
import urllib.parse
import urllib.request
import os



def fetch(url: str, idx: int) -> None:
    full_url = f"{url}?{urllib.parse.urlencode({'client_id': idx})}"
    try:
        with urllib.request.urlopen(full_url, timeout=10) as response:
            body = response.read().decode('utf-8')
            payload = json.loads(body)
            print(
                f"[{idx:03d}] status={response.status} pid={payload.get('pid')} "
                f"cpu={os.sched_getcpu()} path={payload.get('path')} client_id={payload.get('client_id')}"
            )
    except urllib.error.HTTPError as exc:
        print(f"[{idx:03d}] HTTP ERROR {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        print(f"[{idx:03d}] URL ERROR: {exc.reason}")
    except Exception as exc:
        print(f"[{idx:03d}] ERROR: {exc}")


def run_load_test(base_url: str, requests: int, concurrency: int) -> None:
    url = f"{base_url.rstrip('/')}/debug/worker-info"
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(fetch, url, i) for i in range(1, requests + 1)]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generador de peticiones concurrentes para testear el balanceador de trabajo."
    )
    parser.add_argument("--url", default="http://localhost:8000", help="URL base del servidor FastAPI.")
    parser.add_argument("--requests", type=int, default=50, help="Cantidad total de peticiones.")
    parser.add_argument("--concurrency", type=int, default=10, help="Cantidad de peticiones concurrentes.")
    args = parser.parse_args()

    run_load_test(args.url, args.requests, args.concurrency)


if __name__ == "__main__":
    main()
