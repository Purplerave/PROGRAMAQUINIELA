from pathlib import Path

import settings


def test_required_project_files_exist():
    assert settings.CONFIG_PATH.is_file()
    assert settings.RAW_BASE.joinpath("PRIMERA").is_dir()
    assert settings.RAW_BASE.joinpath("SEGUNDA").is_dir()


def test_historical_csvs_are_packaged():
    csv_files = list(Path(settings.RAW_BASE).rglob("*.csv"))
    assert len(csv_files) == 32
