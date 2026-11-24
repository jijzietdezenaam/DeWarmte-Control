"""COP-statistiek: python3 tests/test_copstats.py"""
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "dewarmte"))
from copstats import CopStats  # noqa: E402

T0 = 1795510000                                   # 24 nov 2026


def test_cop_without_defrost_and_periods():
    c = CopStats()
    v = {"ao_pm_energy": 100.0, "ao_hm_energy": 300.0, "pt_pm_energy": 10.0, "pt_hm_energy": 25.0}
    c.update(v, False, time.localtime(T0))
    for i in range(10):                                   # 1 stap ontdooien: stroom zonder warmte
        v = {**v, "ao_pm_energy": v["ao_pm_energy"] + 0.1, "ao_hm_energy": v["ao_hm_energy"] + (0 if i == 5 else 0.35)}
        c.update(v, i == 5, time.localtime(T0))
    v = {**v, "pt_pm_energy": 10.5, "pt_hm_energy": 26.25}
    c.update(v, False, time.localtime(T0))
    a = c.attrs("ao", "week")
    assert a["cop"] == 3.5 and a["cop_met_ontdooien"] == 3.15 and a["ontdooiverlies_pct"] == 10.0, a
    assert c.value("pt", "month") == 2.5 and c.value("total", "lifetime") == 3.14
    v = {**v, "ao_pm_energy": v["ao_pm_energy"] + 0.1, "ao_hm_energy": v["ao_hm_energy"] + 0.4}
    c.update(v, False, time.localtime(T0 + 7 * 86400))   # nieuwe week en maand
    assert c.attrs("ao", "month")["periode"] == "2026-12" and c.attrs("ao", "month")["vorige_periode"]["cop"] == 3.5
    assert c.attrs("ao", "week")["periode"] == "2026-W49" and c.value("ao", "year") == 3.55
    c2 = CopStats(c.export())                             # na herstart
    assert c2.value("ao", "year") == 3.55


def test_glitches_skipped():
    c = CopStats()
    c.update({"ao_pm_energy": 10.0, "ao_hm_energy": 30.0}, False, time.localtime(T0))
    c.update({"ao_pm_energy": 9.0, "ao_hm_energy": 31.0}, False, time.localtime(T0))       # meter terug
    c.update({"ao_pm_energy": 9.5, "ao_hm_energy": 32.0, "ao_hm_error": 256}, False, time.localtime(T0))
    c.update({"ao_pm_energy": 9.6, "ao_hm_energy": 32.4}, False, time.localtime(T0))
    assert c.attrs("ao", "week")["stroom_kwh"] == 0.1 and c.value("ao", "week") == 4.0   # alleen de laatste, schone stap


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
