"""Firma HMAC-SHA256 con marca de tiempo para webhooks (sin dependencias de Django).

Cabecera:  X-Vecinos-Signature: t=<unix>,v1=<hex>
v1 = HMAC_SHA256(secreto, f"{t}." + cuerpo)
El receptor debe recalcularla y rechazar marcas de tiempo viejas (anti-replay).
"""
import hashlib
import hmac
import time

TOLERANCIA_SEGUNDOS = 300


def firmar(secreto, cuerpo, timestamp=None):
    ts = int(time.time()) if timestamp is None else int(timestamp)
    mac = hmac.new(
        secreto.encode(), f'{ts}.'.encode() + cuerpo, hashlib.sha256
    ).hexdigest()
    return f't={ts},v1={mac}'


def verificar(secreto, cabecera, cuerpo, ahora=None, tolerancia=TOLERANCIA_SEGUNDOS):
    try:
        partes = dict(p.split('=', 1) for p in cabecera.split(','))
        ts = int(partes['t'])
        recibida = partes['v1']
    except (AttributeError, KeyError, ValueError):
        return False
    ahora = time.time() if ahora is None else ahora
    if abs(ahora - ts) > tolerancia:
        return False
    esperada = hmac.new(secreto.encode(), f'{ts}.'.encode() + cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, recibida)
