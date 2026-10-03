"""Der Stripe-Testlauf (werkzeuge/stripe_testlauf.py) weigert sich außerhalb
des Testmodus — er darf nie gegen echte Konten oder mybabu.io laufen."""
import importlib.util
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "stripe_testlauf", HIER.parents[2] / "werkzeuge" / "stripe_testlauf.py")
testlauf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(testlauf)


def test_ohne_test_schluessel_abbruch(monkeypatch, capsys):
    monkeypatch.setenv("BABU_STRIPE_SCHLUESSEL", "rk_live_x")
    with pytest.raises(SystemExit) as e:
        testlauf.main([])
    assert e.value.code == 2 and "Test-Schlüssel" in capsys.readouterr().out


def test_auf_mybabu_abbruch(monkeypatch, capsys):
    monkeypatch.setenv("BABU_STRIPE_SCHLUESSEL", "rk_test_x")
    monkeypatch.setattr(testlauf.bw, "PORTAL_ORIGIN", "https://mybabu.io")
    with pytest.raises(SystemExit) as e:
        testlauf.main([])
    assert e.value.code == 2 and "mybabu.io" in capsys.readouterr().out
