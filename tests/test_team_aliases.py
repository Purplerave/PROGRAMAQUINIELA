import pytest

from PREPARAR_ESTADISTICAS_TEMPORADA_2026_27 import build_alias_index


def test_team_alias_index_keeps_unique_mappings():
    index = build_alias_index(
        ["Real Madrid", "Atletico de Madrid"],
        {
            "Real Madrid": ["Real Madrid", "Madrid Real"],
            "Atletico de Madrid": ["Atletico Madrid"],
        },
    )
    assert index["Madrid Real"] == "Real Madrid"
    assert index["Atletico Madrid"] == "Atletico de Madrid"


def test_team_alias_index_rejects_cross_team_collisions():
    with pytest.raises(ValueError, match="Alias duplicado.*Madrid"):
        build_alias_index(
            ["Real Madrid", "Atletico de Madrid"],
            {
                "Real Madrid": ["Madrid"],
                "Atletico de Madrid": ["Madrid"],
            },
        )
