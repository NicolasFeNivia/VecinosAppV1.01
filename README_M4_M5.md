# M4 (API de producción) y M5 (eventos y asincronía)

Se agregaron dos apps nuevas, `api` y `eventos`. **No se modificó ningún archivo de M1**
(`incidencias/`, plantillas, pruebas, migraciones). Los únicos archivos existentes que
recibieron líneas *al final* (sin tocar lo anterior) son `vecinosapp/settings.py`,
`vecinosapp/urls.py` y `requirements.txt`.

## Puesta en marcha

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py test api eventos incidencias      # sin Redis: las pruebas no lo necesitan
python manage.py runserver
```

- Documentación interactiva: <http://localhost:8000/api/v1/docs/>  ·  esquema: `/api/v1/schema/`
- Worker: `celery -A eventos.celery_app worker -l info`
- Beat (despacho de respaldo cada 30 s y escalamiento por SLA cada 15 min):
  `celery -A eventos.celery_app beat -l info`
- Sin Redis para desarrollo: `CELERY_EAGER=1 python manage.py runserver`
- Redis ya está en `docker-compose.yml`; broker configurable con `CELERY_BROKER_URL`.

## M4 – API `/api/v1/`

| Método y ruta | Quién | Notas |
|---|---|---|
| `POST auth/token/`, `auth/token/refresh/`, `auth/token/blacklist/` | todos | JWT; el refresh **rota** y el anterior queda en lista negra |
| `GET incidencias/` | autenticado | Mismas reglas de visibilidad que la web; cursor (`?limite=`, `next`/`previous`); filtros `estado`, `categoria`, `prioridad`, `q`; ETag |
| `POST incidencias/` | residente con edificio | `Idempotency-Key` |
| `GET incidencias/{id}/` | quien la ve | ETag / `If-None-Match` → 304. Otro edificio → 404 |
| `POST incidencias/{id}/estado/` | admin o técnico asignado | Llama a `services.cambiar_estado`; `If-Match` → 412 si cambió |
| `POST incidencias/{id}/reabrir/` | admin | `services.reabrir` |
| `POST incidencias/{id}/asignar/` | admin | `services.asignar_tecnico` (`tecnico: null` quita) |
| `GET/POST incidencias/{id}/comentarios/` | quien la ve | |
| `GET/POST incidencias/{id}/adjuntos/` | dueño, admin, técnico asignado | multipart; se valida el **contenido real** (firma PNG/JPEG/WEBP/GIF/PDF), el tipo y la extensión los decide el servidor; máx. 5 MB |
| `/webhooks/` (CRUD) | admin | El secreto HMAC se muestra **solo al crear** |

- **Errores de negocio** → `422 {"codigo": "transicion_invalida" | "asignacion_invalida" | "regla_de_negocio", "detalle": "..."}`.
- **Idempotencia**: misma clave + mismo cuerpo → misma respuesta con `Idempotent-Replayed: true`;
  misma clave + otro cuerpo → 422; las claves son por usuario; solo se guardan respuestas 2xx.
- **Límites de uso**: 120/min por usuario (o IP si es anónimo) y 600/min por edificio (`settings.py`).
- **Sin N+1**: `IncidenciaSerializer.optimizar()` hace `select_related`/`prefetch_related`/`annotate`;
  hay una prueba que lo comprueba.
- **Contrato**: `api/tests.py` valida el esquema (`spectacular --validate`) y que no haya migraciones
  pendientes. Para las pruebas generadas con schemathesis: `scripts/contrato_schemathesis.sh`.

### Webhooks firmados

Cabeceras: `X-Vecinos-Event`, `X-Vecinos-Delivery` (id para deduplicar reintentos) y
`X-Vecinos-Signature: t=<unix>,v1=<hex>` con `v1 = HMAC_SHA256(secreto, "<t>." + cuerpo)`.
El receptor debe recalcularla con el cuerpo crudo y rechazar `t` con más de 5 minutos.
Referencia: `eventos/firma.py::verificar`. Eventos: `incidencia.creada`, `.estado_cambiado`,
`.resuelta`, `.tecnico_asignado`, `.reabierta`, `.sla_vencida` (por defecto un endpoint solo recibe
`incidencia.resuelta`).

## M5 – Eventos y asincronía

1. `services.*` (M1) registra un `EventoIncidencia` **dentro de su transacción**.
2. `eventos/signals.py` reacciona a ese evento y escribe filas en `Outbox` **en esa misma
   transacción** (una fila por entrega: correo o webhook). Si la transacción se revierte, no queda
   ningún mensaje. Al confirmar (`transaction.on_commit`) se publica en Celery.
3. `eventos.servicios.entregar` reclama el mensaje con un `UPDATE` condicional atómico (solo un
   worker a la vez, con *lease* de 60 s), envía y marca `entregado`. Si falla: reintento con espera
   exponencial (30 s, 60 s, 120 s … tope 1 h); tras 6 intentos pasa a `fallido` (cola de errores,
   visible en el admin). Un endpoint inexistente va directo a `fallido`.
4. Si Redis o el worker caen, el mensaje sigue en la tabla; beat (`despachar_pendientes`) recoge los
   pendientes y los de *lease* vencido.
5. Escalamiento por SLA (`eventos/sla.py`): alta 4 h, media 24 h, baja 72 h; avisa a los
   administradores del edificio y sube la prioridad a *alta*, una sola vez por incidencia.
6. Preferencias: tabla `PreferenciaNotificacion` (por defecto todo activo).

**Cambio de comportamiento a propósito:** el `post_save` del MVP que enviaba el correo de
"incidencia resuelta" se **desconecta** en `eventos/apps.py` (sin editar `signals.py`); ahora ese
correo sale por el outbox. Si no quieres esto, quita `'eventos'` de `INSTALLED_APPS`.

**Garantía real:** entrega *al menos una vez* sin pérdidas, y deduplicada en todo lo que depende de
nosotros. La prueba de caos (`eventos/tests.py::PruebaDeCaosTest`) mata al worker a mitad del envío y
comprueba que el correo sale una sola vez al recuperarse. Si el proceso muriera *justo después* de que el
servidor SMTP o el webhook aceptó el mensaje y *antes* de marcarlo, se reenviaría; en webhooks el
receptor lo detecta con `X-Vecinos-Delivery`.

## Pendiente / no incluido

- Reto avanzado de M4: URL prefirmada a almacenamiento de objetos (hoy la subida es directa y verificada).
- Reto avanzado de M1 (SLA con pausa de reloj): el SLA de M5 es simple, sin pausa.
- Los webhooks no bloquean IPs privadas (SSRF); hazlo antes de exponer la API en producción.
