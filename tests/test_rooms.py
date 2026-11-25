"""Simulatie van de zelflerende kamerregeling: python3 tests/test_rooms.py"""
import math, os, random, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "dewarmte"))
from rooms import RoomCfg, RoomController, RoomModel, parse_room_config  # noqa: E402

TRUE = {"climate.woonkamer": dict(a=0.06, af=0.15, b=0.06, d=0.2), "climate.finn": dict(a=0.16, af=0.0, b=0.04, d=0.1)}


def cfgs():
    return [RoomCfg("climate.woonkamer", "Woonkamer", "s.w", "c.w", "n.wo", "n.wc", 20.5, 19, "fan.jaga"),
            RoomCfg("climate.finn", "Finn", "s.f", "c.f", "n.fo", "n.fc", 19, 18)]


def simulate(days=4, seed=1, window_at=None):
    rnd = random.Random(seed)
    ctl = RoomController(cfgs())
    temp = {"climate.woonkamer": 18.5, "climate.finn": 18.0}
    emis = {k: 0.0 for k in temp}
    wall0, writes, log = 1_800_000_000.0, {k: 0 for k in temp}, []
    ts = 35.0
    for step in range(int(days * 1440)):
        wall = wall0 + step * 60
        h = (step / 60) % 24
        to = 4 + 4 * math.sin((h - 9) / 24 * 2 * math.pi)
        night = h >= 23 or h < 6
        targets = {"climate.woonkamer": 19.0 if night else 20.5, "climate.finn": 18.0 if night else 19.0}
        meas = {k: round(t + rnd.gauss(0, 0.03), 1) for k, t in temp.items()}
        curve = 37 - 0.5 * to
        need = ctl.supply_need(targets, to, curve, meas, wall)
        w = need["weight"]
        model = need["supply"] if need["supply"] is not None else curve
        ts += 0.05 * ((curve + w * (model - curve)) - ts)
        for k, c in ctl.rooms.items():
            ctl.observe(k, wall, meas[k], to, ts, True)
            d = ctl.decide(k, wall, meas[k], targets[k], to, ts, True)
            if d["write"]:
                ctl.wrote_valve(k, d["u"], wall); writes[k] += 1
            if d["fan_write"]:
                ctl.wrote_fan(k, d["fan"], wall)
            p = TRUE[k]
            rs = ctl.state[k]
            u = rs.u or 0.0
            open_window = window_at is not None and k == "climate.finn" and window_at <= step < window_at + 15
            e = (p["a"] + p["af"] * rs.fan) * u * max(0, ts - temp[k])
            emis[k] += (e - emis[k]) * (1 - math.exp(-1 / 15))                        # radiator: 15 min traag
            loss = p["b"] * (temp[k] - to) + (8 if open_window else 0) * (temp[k] - to) / 10
            temp[k] += (emis[k] - loss + p["d"]) / 60
        if step % 60 == 0:
            log.append((step / 1440, {k: (round(temp[k], 2), targets[k], ctl.state[k].u) for k in temp}, round(ts, 1), w))
    return ctl, log, writes


def test_learning_and_tracking():
    ctl, log, writes = simulate(days=4)
    m = ctl.models
    print("geleerd woonkamer:", [round(x, 3) for x in m["climate.woonkamer"].theta], "conf", m["climate.woonkamer"].confidence)
    print("geleerd finn     :", [round(x, 3) for x in m["climate.finn"].theta], "conf", m["climate.finn"].confidence)
    # laatste 2 dagen: kamer binnen 0,5 K van het doel (behalve vlak na een doelstap)
    errs = {k: [] for k in TRUE}
    for t, rooms, ts, w in log:
        if t < 2:
            continue
        hour = round((t % 1) * 24)
        if hour in (23, 0, 6, 7):                        # overgangen dag/nacht overslaan
            continue
        for k, (temp, target, u) in rooms.items():
            errs[k].append(abs(temp - target))
    for k, e in errs.items():
        mean = sum(e) / len(e)
        print(f"{k}: gemiddelde afwijking {mean:.2f} K, max {max(e):.2f} K, klepwrites {writes[k]} in 4 dagen")
        assert mean < 0.35 and max(e) < 1.0, (k, mean, max(e))
        assert writes[k] < 4 * 24 * 1.5, writes              # gemiddeld < 1,5 klepwijziging per uur
    assert m["climate.woonkamer"].confidence == 1.0
    assert abs(m["climate.woonkamer"].b - 0.06) < 0.04 and abs(m["climate.finn"].a - 0.16) < 0.08
    ts_last = [ts for t, r, ts, w in log if t > 3]
    print("aanvoer laatste dag:", min(ts_last), "-", max(ts_last), "°C, gewicht model", log[-1][3])
    assert log[-1][3] == 1.0


def test_window_detection():
    ctl, log, writes = simulate(days=1, window_at=600)
    rs = ctl.state["climate.finn"]
    assert rs.window_until > 0
    print("raam: klep dicht tot", rs.window_until)


def test_overheat_and_off_and_parse():
    ctl = RoomController(cfgs())
    d = ctl.decide("climate.finn", 1e9, 20.0, 19.0, 5, 35, True)
    assert d["u"] == 0.0 and d["write"]
    ctl.mode["climate.finn"] = "off"
    assert ctl.decide("climate.finn", 1e9 + 60, 15.0, 19.0, 5, 35, True)["u"] == 0.0
    assert ctl.decide("climate.finn", 1e9 + 120, 6.0, 19.0, 5, 35, True)["u"] == 1.0     # vorst
    ctl.mode["climate.finn"] = "heat"
    d = ctl.decide("climate.finn", 1e9 + 180, 17.5, 19.0, 5, 35, True)
    assert d["u"] == 1.0                                  # 1,5 K te koud: open
    ctl.wrote_valve("climate.finn", 1.0, 1e9 + 180)
    d = ctl.decide("climate.finn", 1e9 + 240, 18.9, 19.0, 5, 35, True)
    assert d["u"] < 1.0 and not d["write"]                # binnen 10 min: niet opnieuw schrijven
    st = RoomController(cfgs(), ctl.export_state())
    assert st.mode == ctl.mode and st.models["climate.finn"].theta == ctl.models["climate.finn"].theta
    rows = parse_room_config("climate.a | A | sensor.a | climate.ta | number.o | number.c | 20,5 | 19 | fan.x\nonzin\n"
                             "climate.b | B | sensor.b | climate.tb | number.o2 | number.c2 | 19 | 18")
    assert [r.key for r in rows] == ["climate.a", "climate.b"] and rows[0].fan == "fan.x" and rows[1].fan is None
    assert rows[0].day == 20.5



def test_quality_gate_sensor_reset_and_fans():
    ctl = RoomController(cfgs())
    m = ctl.models["climate.woonkamer"]
    m.n, m.err = 200, 0.2
    assert m.confidence == 1.0
    m.err = 1.4                                            # voorspelt slecht: standaardwaarden
    assert m.confidence == 0.0 and m.eff()[0] == 0.10
    st = ctl.export_state()
    other = cfgs(); other[0].sensor = "sensor.nieuw"
    fresh = RoomController(other, st)
    assert fresh.models["climate.woonkamer"].n == 0 and fresh.models["climate.finn"].n == ctl.models["climate.finn"].n
    same = RoomController(cfgs(), st)
    assert same.models["climate.woonkamer"].n == 200
    old = {"models": {k: {kk: vv for kk, vv in v.items() if kk != "sensor"} for k, v in st["models"].items()}}
    mig = RoomController(cfgs(), old)                      # oude opslag zonder sensor: slecht model opnieuw
    assert mig.models["climate.woonkamer"].n == 0 and mig.models["climate.finn"].n == ctl.models["climate.finn"].n
    m.err = 0.2                                            # betrouwbaar model voor de aanvoerberekening
    t = {"climate.woonkamer": 20.5, "climate.finn": None}
    temps = {"climate.woonkamer": 20.0, "climate.finn": 19.0}
    with_fan = ctl.supply_need(t, 0.0, 28.0, temps, 1e9, {"climate.woonkamer"})["supply"]
    no_fan = ctl.supply_need(t, 0.0, 28.0, temps, 1e9, set())["supply"]
    assert no_fan > with_fan, (no_fan, with_fan)
    m.err = 1.4                                            # onbetrouwbaar: telt niet mee voor de aanvoer
    assert ctl.supply_need(t, 0.0, 28.0, temps, 1e9, set())["supply"] is None



def test_no_overshoot_cycles_with_slow_radiator():
    """Radiator met 30 min vertraging en een model dat de afgifte onderschat: geen schommel-cyclus."""
    for true in (dict(a=0.20, b=0.07, d=0.3), dict(a=0.12, b=0.06, d=0.2)):
        cfg = RoomCfg("climate.x", "X", "s", "c", "o", "cl", 19, 18)
        ctl = RoomController([cfg])
        T, rad, ts, to, temps = 17.0, 0.0, 34.0, 0.0, []
        for step in range(30 * 60):
            wall = 1.8e9 + step * 60
            ctl.observe("climate.x", wall, round(T, 2), to, ts, True)
            d = ctl.decide("climate.x", wall, round(T, 2), 19.0, to, ts, True)
            if d["write"]:
                ctl.wrote_valve("climate.x", d["u"], wall)
            u = ctl.state["climate.x"].u or 0
            rad += (u * max(0, ts - T) - rad) * (1 - math.exp(-1 / 30))
            T += (true["a"] * rad - true["b"] * (T - to) + true["d"]) / 60
            temps.append(T)
        late = temps[20 * 60:]
        print(f"  a={true['a']}: max boven doel {max(temps) - 19:+.2f} K, schommeling laatste 10u {max(late) - min(late):.2f} K")
        assert max(temps) - 19 < 0.7 and max(late) - min(late) < 0.45, true



def test_defrost_dip_ignored():
    ctl = RoomController(cfgs())
    k = "climate.finn"
    wall = 1.9e9
    for i in range(60):                                   # stabiel op doel, klep 40 %
        ctl.decide(k, wall + i * 60, 19.0, 19.0, 0.0, 32.0, True)
    ctl.wrote_valve(k, 0.4, wall)
    w = wall + 3600
    ctl.set_defrost(True, w)
    d1 = ctl.decide(k, w + 60, 18.8, 19.0, 0.0, 32.0, True)
    ctl.set_defrost(False, w + 400)
    d2 = ctl.decide(k, w + 1200, 18.85, 19.0, 0.0, 32.0, True)   # nog in herstel
    assert not d1["write"] and not d2["write"] and d1["u"] == 0.4, (d1, d2)
    assert "ontdooien" in d1["why"]
    d3 = ctl.decide(k, w + 1600, 17.5, 19.0, 0.0, 32.0, True)    # echt te koud: wel ingrijpen
    assert d3["u"] == 1.0 and d3["write"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)


def test_no_blind_valve_after_restart():
    ctl = RoomController(cfgs())
    d = ctl.decide("climate.finn", 1_800_000_000.0, None, 19.0, 5.0, 35.0, True)   # nog geen kamertemperatuur
    assert d["write"] is False and ctl.state["climate.finn"].u is None
    d = ctl.decide("climate.finn", 1_800_000_060.0, 18.0, 19.0, 5.0, 35.0, True)   # wel: gewoon regelen
    assert d["write"] is True
