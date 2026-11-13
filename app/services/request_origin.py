"""Same-Origin-Prüfung für HTTP-POSTs und den Terminal-WebSocket.

Browser senden bei fetch()-POSTs und WebSocket-Verbindungen immer einen
Origin-Header. Stimmt dessen Hostname nicht mit dem angefragten Host überein,
stammt der Request von einer fremden Webseite (CSRF bzw. Cross-Site WebSocket
Hijacking) und wird abgelehnt. Der Port wird bewusst nicht verglichen, weil der
Terminal-WebSocket auf einem anderen Port als die Weboberfläche läuft.

Requests ohne Origin-Header (curl, Skripte, Tests) werden zugelassen – sie
können nicht von einer fremden Webseite im Browser des Nutzers stammen.
"""

import urllib.parse


def _hostname(netloc_or_url: str, is_url: bool) -> str | None:
    try:
        target = netloc_or_url if is_url else "//" + netloc_or_url
        host = urllib.parse.urlsplit(target).hostname
    except ValueError:
        return None
    return host.lower().rstrip(".") if host else None


def is_same_origin(origin: str | None, host: str | None) -> bool:
    if origin is None or origin == "":
        return True
    if origin == "null" or not host:
        return False
    origin_host = _hostname(origin, is_url=True)
    request_host = _hostname(host, is_url=False)
    return origin_host is not None and origin_host == request_host
