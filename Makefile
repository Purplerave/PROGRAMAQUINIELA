.PHONY: help test backtest predict reference sanitize economics real-quiniela clean lint audit

PYTHON ?= python3
JORNADA ?= 74

help:
	@echo "Comandos disponibles en Programa Quiniela:"
	@echo "  make audit          - Valida código, datos, pruebas y backtest oficial cerrado"
	@echo "  make lint           - Detecta errores de sintaxis y nombres no definidos"
	@echo "  make test           - Ejecuta la suite completa de pruebas con pytest"
	@echo "  make backtest       - Ejecuta el backtest historico walk-forward por temporadas"
	@echo "  make predict        - Genera diagnostico y paquete para la jornada (ej. JORNADA=74)"
	@echo "  make reference      - Regenera la referencia local (salida/referencia_produccion.json)"
	@echo "  make sanitize       - Ejecuta el saneamiento explicito del historico raw"
	@echo "  make economics      - Ejecuta una simulación económica (premios supuestos, no ROI realizado)"
	@echo "  make real-quiniela  - Comprueba el corpus de boletos y escrutinios oficiales"
	@echo "  make clean          - Elimina archivos temporales y caches localmente"

lint:
	$(PYTHON) -m ruff check --select E9,F821,F822,F823 .
	git diff --check

audit: lint
	@mkdir -p salida
	@evidence=$$(mktemp -d salida/auditoria.XXXXXX) && \
		$(PYTHON) scripts/datos/VALIDAR_DATASETS.py --json "$$evidence/datasets.json"
	$(PYTHON) -m coverage run --branch --source=. -m pytest tests/ -q
	$(PYTHON) -m coverage report --omit='tests/*,LMARENA/*'
	$(PYTHON) scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py --to-season 2025-2026

test:
	$(PYTHON) -m pytest tests/ -q

backtest:
	$(PYTHON) scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py

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

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
