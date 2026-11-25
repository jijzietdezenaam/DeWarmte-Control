"""Zelflerende kamerregeling (puur Python, geen Home Assistant-imports).

Per kamer leert DeWarmte een eenvoudig warmtemodel:

    dT/dt [K/u] = (a + af·fan) · klep · (T_aanvoer − T_kamer) · circulatie − b · (T_kamer − T_buiten) + d

a  = afgifte per K aanvoeroverschot bij een volledig open klep
af = extra afgifte door de radiatorfans (per fractie fan, alleen kamers met fans)
b  = warmteverlies naar buiten
d  = vaste warmtewinst (zon, mensen, apparaten, buurkamers)

Het model wordt met recursieve kleinste kwadraten (RLS) bijgewerkt. Begint met voorzichtige
standaardwaarden; hoe meer metingen, hoe meer het geleerde model meetelt.

Daarmee kiest de regeling:
  * per kamer de klepstand die nodig is om het kamerdoel te halen (plus PI-correctie);
  * voor de woonkamer de fan-stand (20-50 %);
  * de laagste aanvoertemperatuur waarbij de 'moeilijkste' kamer zijn doel haalt met de klep op ~85 %.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

PRIOR = [0.10, 0.10, 0.05, 0.0]          # a, af, b, d
PRIOR_VAR = [0.05 ** 2, 0.10 ** 2, 0.03 ** 2, 0.3 ** 2]
NOISE_VAR = 0.2 ** 2                      # meetruis dT/dt (K/u), 0,1 K-sensor over 30 min
BOUNDS = [(0.01, 0.6), (0.0, 0.6), (0.005, 0.3), (-1.5, 1.5)]
LAMBDA = 0.997                           # vergeetfactor per update (elke 10 min: geheugen ~2 dagen)


@dataclass
class RoomCfg:
    key: str                 # kamer-id, bijv. climate.woonkamer_2 (wordt ook het entity-id na overstap)
    name: str
    sensor: str              # kamertemperatuursensor
    trv: str                 # climate-entiteit van de TRV
    opening: str             # number ..._valve_opening_degree
    closing: str             # number ..._valve_closing_degree
    day: float
    night: float
    fan: str | None = None   # optioneel: fan-entiteit (radiatorventilatoren)
    away: float | None = None        # K lager als niemand thuis is (None = algemene instelling)
    price_down: float | None = None  # max. K lager als stroom duur is (None = algemene instelling)


def _num(text: str) -> float:
    return float(text.strip().replace(",", "."))


def parse_room_config(text: str | None) -> list[RoomCfg]:
    """Eén regel per kamer:
    `climate.woonkamer_2 | Woonkamer | sensor.temp | climate.trv | number.open | number.dicht | 20 | 19 | fan.jaga | afwezig=1 | duur=0,5`

    Na de nachttemperatuur mogen in willekeurige volgorde komen: een fan-entiteit (`fan.…`),
    `afwezig=K` (zoveel lager als niemand thuis is) en `duur=K` (max. zoveel lager bij dure stroom).
    """
    out: list[RoomCfg] = []
    for line in (text or "").replace(";", "\n").splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) < 8 or not p[0].startswith("climate."):
            continue
        try:
            day, night = _num(p[6]), _num(p[7])
        except ValueError:
            continue
        fan = away = price = None
        for extra in p[8:]:
            key, _, val = extra.partition("=")
            key = key.strip().lower()
            try:
                if extra.startswith("fan."):
                    fan = extra
                elif key in ("afwezig", "away") and val:
                    away = max(0.0, _num(val))
                elif key in ("duur", "price") and val:
                    price = max(0.0, _num(val))
            except ValueError:
                continue
        out.append(RoomCfg(p[0], p[1] or p[0], p[2], p[3], p[4], p[5], day, night, fan, away, price))
    return out


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


class RoomModel:
    """RLS-schatting van [a, af, b, d]."""

    def __init__(self, state: dict | None = None) -> None:
        st = state or {}
        self.theta: list[float] = list(st.get("theta") or PRIOR)
        P = st.get("P")
        self.P: list[list[float]] = [list(r) for r in P] if P else [
            [PRIOR_VAR[i] / NOISE_VAR if i == j else 0.0 for j in range(4)] for i in range(4)]
        self.n: int = int(st.get("n", 0))           # updates met warmteafgifte (klep open + circulatie)
        self.n_all: int = int(st.get("n_all", 0))
        self.err: float | None = st.get("err")       # gemiddelde absolute voorspelfout (K/u)

    def export(self) -> dict:
        return {"theta": [round(x, 5) for x in self.theta], "P": [[round(x, 7) for x in r] for r in self.P],
                "n": self.n, "n_all": self.n_all, "err": None if self.err is None else round(self.err, 3)}

    @property
    def a(self) -> float: return self.theta[0]
    @property
    def af(self) -> float: return self.theta[1]
    @property
    def b(self) -> float: return self.theta[2]
    @property
    def d(self) -> float: return self.theta[3]

    @property
    def confidence(self) -> float:
        """0 = alleen standaardwaarden, 1 = ruim 12 uur aan metingen met warmteafgifte én een model dat
        de kamer goed voorspelt. Voorspelt het slecht (bijv. een sensor die zelden meldt), dan telt het
        geleerde model minder of niet mee en regelt DeWarmte met standaardwaarden + bijsturing."""
        quality = 1.0 if self.err is None else _clip((1.0 - self.err) / 0.5, 0.0, 1.0)
        return _clip(self.n / 72, 0.0, 1.0) * quality

    @staticmethod
    def features(u: float, fan: float, ts: float, tr: float, to: float, flowing: float) -> list[float]:
        dt = max(0.0, ts - tr) * flowing
        return [u * dt, u * fan * dt, -(tr - to), 1.0]

    def rate(self, x: list[float]) -> float:
        return sum(t * xi for t, xi in zip(self.theta, x))

    def update(self, x: list[float], y: float, has_fan: bool) -> None:
        if not has_fan:
            x = [x[0], 0.0, x[2], x[3]]
        err = y - self.rate(x)
        self.err = abs(err) if self.err is None else self.err + 0.05 * (abs(err) - self.err)
        if abs(err) > 3.0:                        # uitschieter (raam, douche, zon op sensor): niet leren
            return
        P = self.P
        Px = [sum(P[i][j] * x[j] for j in range(4)) for i in range(4)]
        den = LAMBDA + sum(x[i] * Px[i] for i in range(4))
        k = [v / den for v in Px]
        self.theta = [_clip(self.theta[i] + k[i] * err, *BOUNDS[i]) for i in range(4)]
        new = [[(P[i][j] - k[i] * Px[j]) / LAMBDA for j in range(4)] for i in range(4)]
        for i in range(4):                       # geen opblazen bij weinig variatie (windup)
            cap = PRIOR_VAR[i] / NOISE_VAR
            if new[i][i] > cap:
                s = math.sqrt(cap / new[i][i])
                for j in range(4):
                    new[i][j] *= s
                    new[j][i] *= s
        self.P = new
        self.n_all += 1
        if x[0] > 1.0:
            self.n += 1

    def eff(self) -> list[float]:
        """Waarden om mee te regelen: standaardwaarden, naarmate er meer geleerd is geleidelijk de geleerde.
        Zo kan één vreemde meting in het begin de regeling niet van slag brengen."""
        c = self.confidence
        return [p + c * (t - p) for p, t in zip(PRIOR, self.theta)]

    def capacity(self, fan: float, ts: float, tr: float) -> float:
        """Afgifte (K/u) bij een volledig open klep."""
        a, af, _, _ = self.eff()
        return (a + af * fan) * max(0.0, ts - tr)

    def steady_need(self, target: float, to: float) -> float:
        """Benodigde afgifte (K/u) om het doel vast te houden."""
        _, _, b, d = self.eff()
        return max(0.0, b * (target - to) - d)


@dataclass
class RoomState:
    u: float | None = None                   # gecommandeerde klep 0..1 (laatst geschreven)
    u_t: float = 0.0                         # wall van laatste klepwrite
    u_want: float | None = None              # gewenste klep (voor dashboard)
    fan: float = 0.0                         # gecommandeerde fan 0..1
    fan_t: float = 0.0
    integ: float = 0.0                       # I-term (fractie klep)
    window_until: float = 0.0
    hist: deque = field(default_factory=lambda: deque(maxlen=12))       # (wall, tr) laatste ~15 min
    samples: deque = field(default_factory=lambda: deque(maxlen=12))    # (wall, tr, u, fan, ts, to, flow) per 5 min
    last_sample: float = 0.0
    last_learn: float = 0.0
    last_step: float | None = None
    reason: str = "start"
    tr_f: float | None = None                # gefilterde kamertemperatuur (tegen 0,1 K-sprongen)
    rate: float = 0.0                        # temperatuurverloop (K/u), gefilterd
    trv_ok: bool = True


@dataclass
class RoomSettings:
    u_design: float = 0.85         # aanvoer zo kiezen dat de moeilijkste kamer hier uitkomt
    kp: float = 1.2                # K/u extra afgifte per K (verwacht) tekort
    ki: float = 0.08               # klepfractie per K·uur (traag: radiatoren reageren met ~30 min vertraging)
    full_open_k: float = 1.2       # zoveel te koud: klep volledig open
    lead_h: float = 0.5            # vooruitkijken: regelen op de verwachte temperatuur over een half uur
    i_leak_h: float = 0.0          # I-term lekt weg met deze tijdconstante (uur, 0 = niet)
    i_max: float = 0.30
    min_open: float = 0.10         # kleiner dan dit: dicht (voorkomt druppelen en pendelen)
    write_step: float = 0.10       # pas schrijven bij ≥ 10 % verschil (spaart TRV-batterijen)
    write_min_s: float = 900.0     # klep max. 1x per 15 min wijzigen (behalve dicht/open bij te warm/te koud)
    fan_min: float = 0.20
    fan_max: float = 0.50
    fan_min_s: float = 300.0
    window_drop_k: float = 0.8     # ≥ 0,8 K daling binnen 15 min (sensoren melden in stapjes, dus niet te gevoelig)
    window_s: float = 1800.0
    overheat_k: float = 0.5
    ff_fade_k: float = 0.4         # boven doel: vasthoudwarmte lineair naar 0 over zoveel K
    frost: float = 7.0
    defrost_hold_s: float = 1500.0 # na ontdooien zo lang (25 min) niet bijsturen: aanvoer moet nog herstellen
    supply_down: float = 6.0       # modelaanvoer max. zoveel onder de stooklijn
    supply_up: float = 3.0         # en max. zoveel erboven


class RoomController:
    def __init__(self, rooms: list[RoomCfg], state: dict | None = None, settings: RoomSettings | None = None,
                 no_window: set[str] | None = None) -> None:
        self.s = settings or RoomSettings()
        # kamers die met de sensor in de TRV meten: die sensor koelt snel af als de klep dichtgaat,
        # dat lijkt op een open raam. Daar geen raamdetectie.
        self.no_window = set(no_window or ())
        self.defrost_active = False
        self.defrost_until = 0.0          # tot dan: ontdooien + herstel van de aanvoer, kleppen niet bijsturen
        self.rooms = {r.key: r for r in rooms}
        st = state or {}
        models = st.get("models") or {}
        # opnieuw beginnen bij een andere sensor dan waarmee geleerd is, en (overgang vanaf versies die
        # de sensor nog niet bewaarden) bij een model dat de kamer duidelijk slecht voorspelt
        def keep(st: dict | None, sensor: str) -> dict | None:
            if not st:
                return None
            if "sensor" in st:
                return st if st["sensor"] == sensor else None
            return None if (st.get("err") or 0) > 1.0 else st
        self.models = {k: RoomModel(keep(models.get(k), r.sensor)) for k, r in self.rooms.items()}
        self.mode: dict[str, str] = {k: (st.get("mode") or {}).get(k, "heat") for k in self.rooms}
        self.manual: dict[str, tuple[float, float]] = {k: tuple(v) for k, v in (st.get("manual") or {}).items()
                                                       if k in self.rooms}
        self.state = {k: RoomState(integ=float((st.get("integ") or {}).get(k, 0.0))) for k in self.rooms}

    def export_state(self) -> dict:
        return {"models": {k: {**m.export(), "sensor": self.rooms[k].sensor} for k, m in self.models.items()},
                "mode": self.mode,
                "manual": {k: list(v) for k, v in self.manual.items()},
                "integ": {k: round(s.integ, 3) for k, s in self.state.items()}}

    def set_defrost(self, active: bool, wall: float) -> None:
        """Tijdens ontdooien haalt de warmtepomp warmte uit het water; de kamers zakken kort iets.
        Dat is tijdelijk: daarop niet bijsturen en er niet van leren."""
        self.defrost_active = bool(active)
        if active:
            self.defrost_until = wall + self.s.defrost_hold_s

    # ------------------------------------------------------------ waarnemen en leren
    def observe(self, key: str, wall: float, tr: float | None, to: float | None, ts: float | None,
                flowing: bool) -> None:
        rs, m = self.state[key], self.models[key]
        if tr is None:
            rs.hist.clear()
            rs.samples.clear()
            return
        rs.hist.append((wall, tr))
        while rs.hist and wall - rs.hist[0][0] > 900:
            rs.hist.popleft()
        # raam open: snelle daling
        old = [t for w, t in rs.hist if wall - w <= 900]
        if (key not in self.no_window and old and max(old) - tr >= self.s.window_drop_k
                and wall >= rs.window_until):
            rs.window_until = wall + self.s.window_s
            rs.samples.clear()
        if wall - rs.last_sample < 300:
            return
        rs.last_sample = wall
        if to is None or ts is None or rs.u is None or not rs.trv_ok or wall < rs.window_until:
            rs.samples.clear()
            return
        if rs.samples and wall - rs.samples[-1][0] > 900:
            rs.samples.clear()                                         # gat in de meting
        rs.samples.append((wall, tr, rs.u, rs.fan, ts, to, 1.0 if flowing else 0.0))
        if wall - rs.last_learn < 600:
            return
        # y: temperatuurverloop over de laatste 30 min; x: gemiddelden over 40..10 min geleden (radiatortraagheid)
        first = next((s for s in rs.samples if wall - s[0] <= 1860), None)
        if first is None or wall - first[0] < 1500:
            return
        win = [s for s in rs.samples if 600 <= wall - s[0] <= 2460] or list(rs.samples)
        y = (tr - first[1]) / ((wall - first[0]) / 3600)
        xs = [RoomModel.features(s[2], s[3], s[4], s[1], s[5], s[6]) for s in win]
        x = [sum(c) / len(xs) for c in zip(*xs)]
        rs.last_learn = wall
        if self.defrost_active:
            return                     # tijdens ontdooien niet leren
        m.update(x, y, self.rooms[key].fan is not None)

    # ------------------------------------------------------------ besluiten
    def decide(self, key: str, wall: float, tr: float | None, target: float | None, to: float | None,
               ts: float | None, flowing: bool) -> dict:
        """Gewenste klep (0..1) en fan (0..1) plus of er nu geschreven moet worden."""
        s, rs, m, cfg = self.s, self.state[key], self.models[key], self.rooms[key]
        dt_h = 0.0 if rs.last_step is None else _clip((wall - rs.last_step) / 3600, 0.0, 0.1)
        rs.last_step = wall
        hold = wall < self.defrost_until          # ontdooien of herstel: tijdelijke dip negeren
        if tr is not None:
            prev = rs.tr_f
            rs.tr_f = tr if rs.tr_f is None or abs(tr - rs.tr_f) > 1.0 else rs.tr_f + (
                1 - math.exp(-dt_h * 6)) * (tr - rs.tr_f)                  # tijdconstante 10 min
            if prev is not None and dt_h > 0 and abs(tr - prev) <= 1.0 and not hold:
                inst = _clip((rs.tr_f - prev) / dt_h, -3.0, 3.0)
                rs.rate += (1 - math.exp(-dt_h * 2)) * (inst - rs.rate)    # tijdconstante 30 min
        force = False
        if tr is None:
            u, why = (rs.u if rs.u is not None else 0.5), "geen kamertemperatuur: klep ongewijzigd"
        elif self.mode.get(key) == "off":
            u, why, force = (1.0, "uit, maar vorstbeveiliging", True) if tr < s.frost else (0.0, "uit", True)
        elif target is None:
            u, why = (rs.u if rs.u is not None else 0.5), "geen kamerdoel"
        elif wall < rs.window_until:
            u, why, force = 0.0, "raam open (snelle temperatuurdaling): klep dicht", True
        elif tr >= target + s.overheat_k:
            u, why, force = 0.0, f"{tr - target:.1f} K te warm: klep dicht", True
            rs.integ = min(rs.integ, 0.0)
        else:
            to_ = to if to is not None else 5.0
            ts_ = ts if ts is not None else 35.0
            err = target - (rs.tr_f if rs.tr_f is not None else tr)
            err_p = err - _clip(rs.rate, -2.0, 2.0) * s.lead_h            # verwacht tekort (dempt doorschieten)
            # boven doel: de "vasthoud"-warmte afbouwen (bij +0,4 K niets meer), zodat de klep echt dichtgaat
            ff = m.steady_need(target, to_) * _clip(1.0 + min(0.0, err) / s.ff_fade_k, 0.0, 1.0)
            need = ff + s.kp * err_p
            cap = m.capacity(rs.fan if cfg.fan else 0.0, ts_, tr)
            base = 1.0 if cap < 0.05 else need / cap
            u = base + rs.integ
            full = target - tr >= s.full_open_k
            # anti-windup: alleen integreren als de klep echt geregeld wordt (niet bij vol open/dicht)
            if 0.0 < u < 1.0 and flowing and not full and not hold:
                rs.integ = _clip(rs.integ + s.ki * err_p * dt_h, -s.i_max, s.i_max)
            if s.i_leak_h > 0:
                rs.integ *= math.exp(-dt_h / s.i_leak_h)
            u = _clip(u, 0.0, 1.0)
            why = (f"nodig {max(0.0, need):.2f} K/u, max {cap:.2f} K/u bij {ts_:.0f} °C"
                   f" → {u:.0%} (I {rs.integ:+.0%})")
            if full:
                u, force, why = 1.0, True, f"{target - tr:.1f} K te koud: klep open"
            if u < s.min_open:
                u = 0.0
        u = round(u * 20) / 20                                          # stappen van 5 %
        rs.u_want, rs.reason = u, why
        if hold and not force and rs.u is not None:
            u, why = rs.u, "ontdooien: klep ongewijzigd (tijdelijke dip)"
        write = rs.u is None or (abs(u - rs.u) >= s.write_step - 1e-9 and (
            force or wall - rs.u_t >= s.write_min_s))
        if rs.u is not None and abs(u - rs.u) < 1e-9:
            write = False
        # fan: alleen bij circulatie en klep echt open
        fan = 0.0
        if cfg.fan and flowing and u >= 0.3 and self.mode.get(key) != "off" and wall >= rs.window_until:
            lift = _clip((u - 0.3) / 0.6, 0.0, 1.0)
            if tr is not None and target is not None and target - tr >= 0.3:
                lift = 1.0
            fan = round((s.fan_min + (s.fan_max - s.fan_min) * lift) * 20) / 20
        fan_write = bool(cfg.fan) and abs(fan - rs.fan) >= 0.05 - 1e-9 and (
            fan == 0.0 or rs.fan == 0.0 or wall - rs.fan_t >= s.fan_min_s)
        return {"u": u, "write": write, "fan": fan, "fan_write": fan_write, "why": why}

    def wrote_valve(self, key: str, u: float, wall: float) -> None:
        rs = self.state[key]
        rs.u, rs.u_t = u, wall

    def wrote_fan(self, key: str, fan: float, wall: float) -> None:
        rs = self.state[key]
        rs.fan, rs.fan_t = fan, wall

    # ------------------------------------------------------------ aanvoer
    def supply_need(self, targets: dict[str, float | None], to: float | None, curve: float,
                    temps: dict[str, float | None], wall: float, fans_ok: set[str] | None = None) -> dict:
        """Laagste aanvoer waarbij elke kamer zijn doel haalt met de klep op u_design."""
        s = self.s
        if to is None:
            return {"supply": None, "weight": 0.0, "room": None}
        best = None
        for key, target in targets.items():
            m, rs, cfg = self.models[key], self.state[key], self.rooms[key]
            if (target is None or self.mode.get(key) == "off" or temps.get(key) is None
                    or wall < rs.window_until):
                continue
            if m.confidence < 0.5:
                continue        # onbetrouwbaar model: die kamer wordt bijgestuurd via klep/klepbijsturing
            fan = s.fan_max if cfg.fan and (fans_ok is None or key in fans_ok) else 0.0   # alleen werkende fans
            need = m.steady_need(target, to)
            a, af, _, _ = m.eff()
            per_k = (a + af * fan) * s.u_design
            ts = target + need / per_k if per_k > 0 else curve
            tr = temps.get(key)
            if tr is not None and tr < target - 0.3:                   # achterstand: iets ruimer
                ts += min(3.0, 2.0 * (target - tr))
            if best is None or ts > best[0]:
                best = (ts, key, m.confidence)
        if best is None:
            return {"supply": None, "weight": 0.0, "room": None}
        ts = _clip(best[0], curve - s.supply_down, curve + s.supply_up)
        weights = [self.models[k].confidence for k in targets
                   if targets[k] is not None and self.models[k].confidence >= 0.5]
        weight = min(best[2], sum(weights) / len(weights)) if weights else 0.0
        return {"supply": round(ts, 1), "weight": round(weight, 2), "room": best[1]}
