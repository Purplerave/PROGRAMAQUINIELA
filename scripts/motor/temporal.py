"""Cortes para datos de fútbol sin hora de finalización certificada."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd


LOCAL_TIMEZONE = "Europe/Madrid"


def _parse_timestamp(value: object) -> pd.Timestamp:
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, (date, datetime)) and not pd.isna(value):
            return pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError(f"Fecha ISO inválida: {value!r}")


def utc_timestamp(value: object) -> pd.Timestamp:
    """Interpreta fechas sin zona como hora de Madrid y compara instantes en UTC."""
    ts = _parse_timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(LOCAL_TIMEZONE, ambiguous="NaT", nonexistent="NaT")
        if pd.isna(ts):
            raise ValueError(f"Hora local ambigua o inexistente: {value!r}; indica el offset")
    return ts.tz_convert("UTC")


def local_timestamp(value: object) -> pd.Timestamp:
    """Fecha y hora civil en Madrid, para agrupar el histórico por día."""
    return utc_timestamp(value).tz_convert(LOCAL_TIMEZONE).tz_localize(None)


def history_before(history: pd.DataFrame, cutoff: object) -> pd.DataFrame:
    """Devuelve solo partidos de días anteriores al corte, nunca los del día.

    ``date`` en el histórico es una fecha de partido, no la hora en que su
    resultado estuvo disponible. La medianoche local es el límite conservador.
    """
    cutoff_day = local_timestamp(cutoff).normalize()
    dates = pd.to_datetime(history["date"], errors="coerce", format="mixed")
    if isinstance(dates.dtype, pd.DatetimeTZDtype):
        dates = dates.dt.tz_convert(LOCAL_TIMEZONE).dt.tz_localize(None)
    elif not pd.api.types.is_datetime64_any_dtype(dates):
        def as_local(value: object) -> pd.Timestamp:
            try:
                return local_timestamp(value)
            except ValueError:
                return pd.NaT

        dates = pd.to_datetime(dates.map(as_local))
    eligible = dates < cutoff_day
    return history.loc[eligible].assign(date=dates.loc[eligible])
