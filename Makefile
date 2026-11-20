.PHONY: help test test-fast backtest ligaf-backtest predict reference sanitize economics real-quiniela clean lint lock audit anidado procedencia registro-verificar

PYTHON ?= python3
JORNADA ?= 74

help:
	@echo "Comandos disponibles en Programa Quiniela:"
	@echo "  make audit          - Valida código, datos, pruebas y backtests de LaLiga y Liga F"
	@echo "  make lint           - Ruff completo (config en pyproject.toml) + comprobación del diff"
	@echo "  make test           - Ejecuta la suite completa de pruebas con pytest"
	@echo "  make test-fast      - Suite sin pruebas marcadas como lentas"
	@echo "  make backtest       - Ejecuta el backtest historico walk-forward por temporadas"
	@echo "  make anidado        - Walk-forward anidado: reajusta pesos y bandas fuera de muestra"
	@echo "  make ligaf-backtest - Evalua Liga F con histórico multitemporada y cortes diarios"
	@echo "  make predict        - Genera diagnostico y paquete para la jornada (ej. JORNADA=74)"
	@echo "  make reference      - Regenera la referencia local (salida/referencia_produccion.json)"
	@echo "  make sanitize       - Ejecuta el saneamiento explicito del historico raw"
	@echo "  make economics      - Ejecuta una simulación económica (premios supuestos, no ROI realizado)"
	@echo "  make real-quiniela  - Comprueba el corpus de boletos y escrutinios oficiales"
	@echo "  make lock           - Regenera los locks con hashes (requiere pip-tools)"
	@echo "  make procedencia    - Verifica el manifiesto de procedencia/licencias de datos"
	@echo "  make registro-verificar - Comprueba la cadena del registro prospectivo append-only"
	@echo "  make clean          - Elimina archivos temporales y caches localmente"

lint:
	$(PYTHON) -m ruff check .
	git diff --check

audit: lint
	@mkdir -p salida
	@evidence=$$(mktemp -d salida/auditoria.XXXXXX) && \
		$(PYTHON) scripts/datos/VALIDAR_DATASETS.py --json "$$evidence/datasets.json"
	$(PYTHON) -m coverage run --branch --source=. -m pytest tests/ -q
	$(PYTHON) -m coverage report --omit='tests/*,LMARENA/*'
	$(PYTHON) scripts/datos/VERIFICAR_PROCEDENCIA.py
	$(PYTHON) scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py --to-season 2025-2026
	$(PYTHON) scripts/backtests/BACKTEST_LIGAF_MULTITEMPORADA.py

test:
	$(PYTHON) -m pytest tests/ -q

test-fast:
	$(PYTHON) -m pytest tests/ -q -m "not slow"

backtest:
	$(PYTHON) scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py

anidado:
	$(PYTHON) scripts/backtests/WALK_FORWARD_ANIDADO.py

ligaf-backtest:
	$(PYTHON) scripts/backtests/BACKTEST_LIGAF_MULTITEMPORADA.py

predict:
	$(PYTHON) MOTOR_DECISION_QUINIELISTICA.py --jornada $(JORNADA)
	$(PYTHON) PREDECIR_JORNADA.py --jornada $(JORNADA)

reference:
	$(PYTHON) scripts/reports/GENERAR_PRODUCTION_REFERENCE.py

sanitize:
	$(PYTHON) scripts/datos/SANEAR_DATOS.py --confirm

economics:
	$(PYTHON) scripts/backtests/EVALUACION_ECONOMICA.py

real-quiniela:
	$(PYTHON) scripts/backtests/QUINIELA_REAL.py

procedencia:
	$(PYTHON) scripts/datos/VERIFICAR_PROCEDENCIA.py

registro-verificar:
	$(PYTHON) scripts/registro_prospectivo.py --verificar

lock:
	$(PYTHON) -m piptools compile --generate-hashes --strip-extras --output-file requirements.lock.txt requirements.in
	$(PYTHON) -m piptools compile --generate-hashes --strip-extras --output-file requirements-dev.lock.txt requirements-dev.in
	$(PYTHON) -m piptools compile --generate-hashes --strip-extras --output-file requirements-tools.lock.txt requirements-tools.in

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
