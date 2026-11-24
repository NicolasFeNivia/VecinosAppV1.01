# M6 (tiempo real y panel) y M7 (pruebas avanzadas)

Apps/carpetas nuevas: `tiempo_real/` y `calidad/`. No se modificó código de M1–M5; solo se
agregaron líneas al final de `settings.py`, `urls.py` y `requirements.txt`.

```bash
pip install -r requirements.txt
python manage.py migrate          # M6 no agrega tablas
python manage.py runserver        # daphne (ASGI) sirve HTTP y WebSockets
python manage.py test             # todo
```
Varios procesos/servidores: `CHANNEL_REDIS_URL=redis://localhost:6379/1` (por defecto, capa en memoria).

## M6
| Ruta | Qué hace |
|---|---|
| `/en-vivo/` | Lista que cambia de estado sola (WebSocket por edificio) |
| `/en-vivo/<id>/` | Detalle que se actualiza sin recargar + registro de eventos |
| `/panel/` (+ `/panel/datos/`) | 4 indicadores con filtros por edificio, técnico y fechas; Chart.js. Solo administrador |
| `/tecnico/` | App mínima instalable (manifest + service worker en `/sw.js`), avisos del navegador |

- WebSockets: `ws/incidencias/<id>/` y `ws/edificios/<id>/`. La autorización se decide **al abrir**
  (reutiliza `incidencias_visibles`); si no, se cierra con código 4403.
- Los mensajes salen de un `post_save` de `EventoIncidencia` con `transaction.on_commit`: no se anuncia nada
  que se haya revertido, y un fallo del canal nunca rompe el cambio de estado.
- Indicadores (`tiempo_real/indicadores.py`, agregaciones en BD): tiempo medio de resolución,
  cumplimiento de SLA (mismos plazos que M5), casos abiertos (valor actual + serie acumulada por día)
  y tasa de reapertura.
- Las páginas originales de M1 no se tocaron, por eso las vistas en vivo son rutas aparte.

**No incluido:** notificaciones push reales con el navegador cerrado (requieren claves VAPID y
`pywebpush`; hoy el aviso se muestra con la pestaña abierta) y el modo sin conexión con cola de comentarios.

## M7
- `calidad/test_dominio_exhaustivo.py`: todas las combinaciones de la tabla de estados (sin BD).
- `calidad/test_propiedades.py`: Hypothesis, secuencias aleatorias de operaciones; verifica que el
  historial es continuo, legal y sin rastro de las operaciones rechazadas.
- `calidad/test_concurrencia.py`: 20 hilos entregando el mismo mensaje del outbox → un solo envío
  (solo PostgreSQL: `DB_ENGINE=postgres python manage.py test calidad.test_concurrencia`).
- Contrato: `api/tests.py` (esquema OpenAPI válido) y `scripts/contrato_schemathesis.sh` (M4).
- Carga: `calidad/locustfile.py`.
- Cobertura con umbral (dominio y casos de uso ≥ 90 %): `scripts/cobertura.sh`.
- Mutación sobre el dominio: `scripts/mutacion.sh`.

Nota: la prueba de concurrencia **de asignación de técnico** (20 hilos sobre la misma incidencia) depende
del bloqueo con `select_for_update` de M3, que este proyecto aún no tiene, por eso no se incluyó.
