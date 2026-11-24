#!/usr/bin/env bash
# M7: umbral de cobertura. El dominio y los casos de uso deben tener >= 90 %.
set -euo pipefail
coverage erase
coverage run manage.py test incidencias api eventos tiempo_real calidad
coverage report --include="incidencias/dominio.py,incidencias/services.py" --fail-under=90
coverage report   # informe completo (informativo)
