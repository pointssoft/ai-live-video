import ipaddress
import socket
from urllib.parse import unquote, urlsplit

from worker.config import WorkerConfig
from worker.errors import WorkerError


def validate_storage_url(url: str, object_key: str, config: WorkerConfig) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" and not (config.allow_insecure_urls and config.app_env in {"local", "test"}):
        raise WorkerError("STORAGE_URL_REJECTED", "VALIDATING_INPUT", False, "Storage URL is not allowed.")
    if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
        raise WorkerError("STORAGE_URL_REJECTED", "VALIDATING_INPUT", False, "Storage URL is not allowed.")
    host = parsed.hostname.encode("idna").decode().lower()
    host_port = f"{host}:{parsed.port}" if parsed.port else host
    if host not in config.allowed_storage_hosts and host_port not in config.allowed_storage_hosts:
        raise WorkerError("STORAGE_URL_REJECTED", "VALIDATING_INPUT", False, "Storage host is not allowed.")
    decoded = unquote(parsed.path)
    if not decoded.endswith("/" + object_key) or ".." in decoded.split("/"):
        raise WorkerError("STORAGE_URL_REJECTED", "VALIDATING_INPUT", False, "Storage path is not allowed.")
    if config.app_env not in {"local", "test"}:
        for result in socket.getaddrinfo(host, parsed.port or 443):
            address = ipaddress.ip_address(result[4][0])
            if not address.is_global:
                raise WorkerError("STORAGE_URL_REJECTED", "VALIDATING_INPUT", False, "Storage address is not allowed.")
