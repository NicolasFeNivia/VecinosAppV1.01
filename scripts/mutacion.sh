#!/usr/bin/env bash
# M7: pruebas de mutación sobre el dominio (mutmut). Si sobrevive un mutante, falta una prueba.
set -euo pipefail
mutmut run --paths-to-mutate incidencias/dominio.py \
  --tests-dir calidad --runner "python -m unittest calidad.test_dominio_exhaustivo"
mutmut results
