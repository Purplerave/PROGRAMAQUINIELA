.PHONY: help test backtest predict reference sanitize economics real-quiniela clean

PYTHON ?= python3
JORNADA ?= 74

help:
	@echo "Comandos disponibles en Programa Quiniela:"
	@echo "  make test           - Ejecuta la suite completa de pruebas con pytest"
	@echo "  make backtest       - Ejecuta el backtest historico walk-forward por temporadas"
	@echo "  make predict        - Genera diagnostico y paquete para la jornada (ej. JORNADA=74)"
	@echo "  make reference      - Regenera el informe de referencia de produccion (reports/production_reference.json)"
	@echo "  make sanitize       - Ejecuta el saneamiento explicito del historico raw"
	@echo "  make economics      - Ejecuta la evaluacion economica (EV/ROI ex-post del boleto)"
	@echo "  make real-quiniela  - Ejecuta el backtest de boletos oficiales y ROI realizado"
	@echo "  make clean          - Elimina archivos temporales y caches localmente"

test:
	$(PYTHON) -m pytest tests/ -q

backtest:
	$(PYTHON) scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py

predict:
	$(PYTHON) MOTOR_DECISION_QUINIELISTICA.py --jornada $(JORNADA)
	$(PYTHON) PREDECIR_JORNADA.py --jornada $(JORNADA)
	$(PYTHON) scripts/datos/PRONOSTICO_FEMENINO_JORNADA.py --jornada $(JORNADA)

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
