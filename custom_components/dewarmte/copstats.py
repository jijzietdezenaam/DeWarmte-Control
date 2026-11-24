"""COP per week / maand / jaar / totaal, met en zonder ontdooien (puur Python)."""
from __future__ import annotations

import time

PERIODS = ("week", "month", "year", "lifetime")
SOURCES = ("ao", "pt", "total")
NAMES = {"week": "deze week", "month": "deze maand", "year": "dit jaar", "lifetime": "totaal"}
SRC_NAMES = {"ao": "pomp AO", "pt": "pomp T", "total": "totaal"}
MAX_STEP_KWH = 5.0            # grotere sprong tussen twee metingen = meter-reset of storing: overslaan


def period_key(period: str, lt: time.struct_time) -> str:
    if period == "week":
        return time.strftime("%G-W%V", lt)                      # ISO-week
    if period == "month":
        return f"{lt.tm_year}-{lt.tm_mon:02d}"
    if period == "year":
        return str(lt.tm_year)
    return "totaal"


def _cop(el: float, th: float) -> float | None:
    return round(th / el, 2) if el >= 0.05 else None


class CopStats:
    def __init__(self, state: dict | None = None) -> None:
        st = state or {}
        self.b: dict = st.get("b") or {}
        self.last: dict = st.get("last") or {}      # laatste meterstanden

    def export(self) -> dict:
        return {"b": self.b, "last": self.last}

    def _slot(self, src: str, period: str, lt: time.struct_time) -> dict:
        key = period_key(period, lt)
        slot = self.b.setdefault(src, {}).setdefault(period, {})
        if slot.get("key") != key:
            if slot.get("key"):
                slot["prev"] = {"periode": slot["key"], **self._numbers(slot)}
            slot.update(key=key, el=0.0, th=0.0, el_d=0.0, th_d=0.0, since=time.strftime("%Y-%m-%d %H:%M", lt))
        return slot

    def add(self, src: str, d_el: float, d_th: float, d_el_def: float, d_th_def: float,
            lt: time.struct_time) -> None:
        for p in PERIODS:
            s = self._slot(src, p, lt)
            s["el"] += d_el
            s["th"] += d_th
            s["el_d"] += d_el_def
            s["th_d"] += d_th_def

    def update(self, v: dict, defrost: bool, lt: time.struct_time | None = None) -> None:
        """v: meterstanden (ao/pt_pm_energy = stroom, ao/pt_hm_energy = warmte, kWh) en foutcodes."""
        lt = lt or time.localtime()
        parts: dict[str, tuple[float, float]] = {}
        for p in ("ao", "pt"):
            el, th = v.get(f"{p}_pm_energy"), v.get(f"{p}_hm_energy")
            if el is None or th is None:
                continue
            prev = self.last.get(p)
            self.last[p] = [el, th]
            if v.get(f"{p}_hm_error"):
                continue                     # warmtemeter in storing: dit stukje niet meetellen
            if not prev:
                continue
            de, dt = el - prev[0], th - prev[1]
            if de < 0 or dt < 0 or de > MAX_STEP_KWH or dt > MAX_STEP_KWH * 8:
                continue
            parts[p] = (de, dt)
        for p, (de, dt) in parts.items():
            if p == "ao" and defrost:
                self.add(p, 0.0, 0.0, de, dt, lt)
            else:
                self.add(p, de, dt, 0.0, 0.0, lt)
        if parts:
            ao = parts.get("ao", (0.0, 0.0))
            pt = parts.get("pt", (0.0, 0.0))
            if defrost:
                self.add("total", pt[0], pt[1], ao[0], ao[1], lt)
            else:
                self.add("total", ao[0] + pt[0], ao[1] + pt[1], 0.0, 0.0, lt)

    @staticmethod
    def _numbers(s: dict) -> dict:
        el, th, el_d, th_d = s.get("el", 0.0), s.get("th", 0.0), s.get("el_d", 0.0), s.get("th_d", 0.0)
        cop_all = _cop(el + el_d, th + th_d)
        cop = _cop(el, th)
        loss = None
        if cop and cop_all:
            loss = round((1 - cop_all / cop) * 100, 1)
        return {"cop": cop, "cop_met_ontdooien": cop_all, "stroom_kwh": round(el, 2), "warmte_kwh": round(th, 2),
                "ontdooien_stroom_kwh": round(el_d, 2), "ontdooien_warmte_kwh": round(th_d, 2),
                "ontdooiverlies_pct": loss}

    def value(self, src: str, period: str) -> float | None:
        s = (self.b.get(src) or {}).get(period)
        return None if not s else self._numbers(s)["cop"]

    def attrs(self, src: str, period: str) -> dict:
        s = (self.b.get(src) or {}).get(period)
        if not s:
            return {}
        return {"periode": s.get("key"), "sinds": s.get("since"), **self._numbers(s),
                "vorige_periode": s.get("prev")}
