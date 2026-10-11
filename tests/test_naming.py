from datetime import date

import pytest

from backend.naming import (
    NULL,
    PATH_MAX,
    combined_file_name,
    final_file_name,
    folder_base_name,
    folder_name,
    input_file_name,
    resolve_collision,
    sanitize,
    x_token,
)

D = date(2026, 10, 11)


def test_sanitize_strips_illegal_and_collapses():
    assert sanitize('  Senior <Backend> / Engineer: "II"  ') == "Senior-Backend-Engineer-II"
    assert sanitize("a   b  c") == "a-b-c"
    assert sanitize("a\t\nb") == "ab"  # control characters are dropped, not treated as spaces
    assert sanitize("...---") is None
    assert sanitize("") is None and sanitize(None) is None
    assert len(sanitize("x" * 100)) == 60


def test_folder_base_name_nulls_and_timestamp():
    assert folder_base_name("R-1", "Acme", "Dev", D) == "R-1_Acme_Dev_2026-10-11"
    assert folder_base_name(None, "Acme", None, D) == f"{NULL}_Acme_{NULL}_2026-10-11"
    assert folder_base_name(None, None, None, D, now_ts=1700000000) == f"{NULL}_{NULL}_{NULL}_2026-10-11_1700000000"


def test_resolve_collision_is_case_insensitive():
    assert resolve_collision("A_B", []) == "A_B"
    assert resolve_collision("A_B", ["a_b"]) == "A_B_2"
    assert resolve_collision("A_B", ["A_B", "A_B_2"]) == "A_B_3"


def test_folder_name_trims_title_to_path_budget():
    long_title = "Principal " * 20
    name = folder_name("R-1", "Acme", long_title, D, base_path_len=PATH_MAX - 60)
    assert len(name) <= 59
    assert name.startswith("R-1_Acme_") and name.endswith("_2026-10-11")


def test_x_token_priority():
    assert x_token("R-1", "Acme", "Dev", D) == "R-1"
    assert x_token(None, "Acme", "Dev", D) == "Acme_Dev"
    assert x_token(None, "Acme", None, D) == "Acme"
    assert x_token(None, None, "Dev", D) == "Dev"
    assert x_token(None, None, None, D) == "2026-10-11"


def test_file_names():
    assert input_file_name(0, "My Resume (final).PDF") == "0_My-Resume-(final).pdf"
    assert input_file_name(3, "noext") == "3_noext"
    assert final_file_name("Jane Doe", "Resume", "R-1", ".PDF") == "Jane-Doe_Resume_R-1.pdf"
    assert combined_file_name("Jane Doe", "Acme_Dev") == "Jane-Doe_Acme_Dev.pdf"
    with pytest.raises(ValueError):
        final_file_name("Jane", "Letter", "x", "pdf")
