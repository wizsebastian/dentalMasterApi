"""Límite de peticiones por dirección para los endpoints públicos.

En memoria y por proceso: la API corre con un solo uvicorn, así que basta. Se
reinicia con la API. Detrás de nginx la dirección llega en X-Forwarded-For.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


def ip_de(request: Request) -> str:
    candidata = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return candidata or (request.client.host if request.client else "desconocida")


def limitar(nombre: str, maximo: int, ventana_s: int) -> Callable[[Request], None]:
    """Dependencia que responde 429 al pasar `maximo` peticiones en `ventana_s` segundos."""
    registro: dict[str, deque[float]] = defaultdict(deque)

    def dependencia(request: Request) -> None:
        ahora = time.monotonic()
        marcas = registro[ip_de(request)]
        while marcas and ahora - marcas[0] > ventana_s:
            marcas.popleft()
        if len(marcas) >= maximo:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Demasiadas peticiones; espera un momento e inténtalo de nuevo",
                headers={"Retry-After": str(ventana_s)},
            )
        marcas.append(ahora)

    dependencia.registro = registro  # type: ignore[attr-defined]  # para las pruebas
    dependencia.__name__ = f"limitar_{nombre}"
    return dependencia
