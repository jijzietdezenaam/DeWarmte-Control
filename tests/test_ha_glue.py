"""Rooktest van de HA-laag met een nep-Home Assistant: python3 tests/test_ha_glue.py"""
import asyncio, dataclasses, importlib.util, os, sys, types, time
from datetime import datetime, timezone

def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m

# ---- stubs
class _Base:
    def __init__(self, *a, **k): pass
@dataclasses.dataclass(frozen=True, kw_only=True)
class _Desc:
    key: str; name: str | None = None; device_class: object = None; state_class: object = None; native_unit_of_measurement: str | None = None; entity_category: object = None; icon: str | None = None
class _E:
    class _C:
        def __getattr__(s, n): return n
    TEMPERATURE=FREQUENCY=POWER=ENERGY=MEASUREMENT=TOTAL_INCREASING=RUNNING=PROBLEM=CONNECTIVITY=VOLTAGE=CURRENT="x"
mod("homeassistant"); mod("homeassistant.components"); mod("homeassistant.helpers")
published = []
subs = {}
async def async_subscribe(hass, topic, cb, qos=0, encoding="utf-8"): subs[topic] = cb; return lambda: None
retained = []
async def async_publish(hass, topic, payload, qos=0, retain=False):
    if topic != "dr164/down": retained.append((topic, payload, retain)); return
    published.append(payload); await DEV(payload)
mod("homeassistant.components.mqtt", async_subscribe=async_subscribe, async_publish=async_publish)
sys.modules["homeassistant.components"].mqtt = sys.modules["homeassistant.components.mqtt"]
mod("homeassistant.config_entries", ConfigEntry=_Base, ConfigFlow=type("CF", (), {"__init_subclass__": classmethod(lambda cls, **k: None)}), OptionsFlow=_Base)
mod("homeassistant.core", HomeAssistant=_Base, callback=lambda f: f)
class Store:
    def __init__(s, *a): pass
    async def async_load(s): return None
    async def async_save(s, d): pass
    def async_delay_save(s, f, d=0): pass
mod("homeassistant.helpers.storage", Store=Store)
class DUC:
    def __init__(s, hass, logger, name=None, config_entry=None, update_interval=None): s.hass = hass
    def __class_getitem__(c, i): return c
    async def async_shutdown(s): pass
    def async_update_listeners(s): pass
class CE:
    def __init__(s, coordinator): s.coordinator = coordinator
mod("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=DUC, CoordinatorEntity=CE)
mod("homeassistant.helpers.entity", DeviceInfo=dict)
notes = []
mod("homeassistant.components.persistent_notification", async_create=lambda hass, msg, title=None, notification_id=None: notes.append((notification_id, title, msg)))
sys.modules["homeassistant.components"].persistent_notification = sys.modules["homeassistant.components.persistent_notification"]
timers = []
mod("homeassistant.helpers.event", async_track_time_change=lambda hass, cb, **kw: timers.append((cb, kw)) or (lambda: None))
mod("homeassistant.components.switch", SwitchEntity=_Base)
mod("homeassistant.components.button", ButtonEntity=_Base)
mod("homeassistant.components.number", NumberEntity=_Base, NumberMode=_E._C())
class HAErr(Exception): pass
mod("homeassistant.exceptions", HomeAssistantError=HAErr, ConfigEntryNotReady=HAErr)
class _Flag(int):
    def __or__(s, o): return _Flag(int(s) | int(o))
class _HV:
    HEAT, OFF, HEATING, IDLE = "heat", "off", "heating", "idle"
mod("homeassistant.components.climate", ClimateEntity=_Base, HVACMode=_HV, HVACAction=_HV,
    ClimateEntityFeature=types.SimpleNamespace(TARGET_TEMPERATURE=_Flag(1), PRESET_MODE=_Flag(16), TURN_ON=_Flag(256), TURN_OFF=_Flag(128)))
mod("homeassistant.const", ATTR_TEMPERATURE="temperature", EntityCategory=_E._C(), PERCENTAGE="%", UnitOfEnergy=_E._C(), UnitOfFrequency=_E._C(), UnitOfPower=_E._C(), UnitOfTemperature=_E._C())
mod("homeassistant.components.sensor", SensorDeviceClass=_E, SensorStateClass=_E, SensorEntity=_Base, SensorEntityDescription=_Desc)
mod("homeassistant.components.binary_sensor", BinarySensorDeviceClass=_E, BinarySensorEntity=_Base, BinarySensorEntityDescription=_Desc)

PKG = os.path.join(os.path.dirname(__file__), "..", "custom_components", "dewarmte")
pkg = types.ModuleType("dewarmte"); pkg.__path__ = [PKG]; sys.modules["dewarmte"] = pkg
def load(n):
    spec = importlib.util.spec_from_file_location(f"dewarmte.{n}", os.path.join(PKG, f"{n}.py"))
    m = importlib.util.module_from_spec(spec); sys.modules[f"dewarmte.{n}"] = m; spec.loader.exec_module(m); return m
bus, regs, const, eng = load("bus"), load("registers"), load("const"), load("engine")
load("params"); load("writes"); load("report"); load("obslog"); coord = load("coordinator"); sens = load("sensor"); binm = load("binary_sensor")
rooms_m = load("rooms"); clim = load("climate"); sw = load("switch"); btn = load("button"); num = load("number"); schema = load("schema"); dash = load("dashboard")
import yaml

# ---- nep-DR164 met de echte registerwaarden
SUN = {0: 4096, 25: 16448, 26: 161, 33: 65535, 34: 65535, 39: 60, 64: 39, 74: 9, 79: 22, 80: 23, 89: 65486,
       769: 28, 772: 1, 773: 1, 775: 2}
PT = {52: 45, 53: 45, 56: 22, 58: 21, 60: 0, 6: 45, 1: 1}
HM14 = {4: 0, 5: 2090, 6: 0, 7: 2049, 8: 0, 9: 41, 12: 0, 13: 7006, 14: 0, 15: 33}
PM5 = {12: 2316, 13: 224, 14: 390, 16: 753, 17: 5002}
PM7 = {12: 2290, 13: 144, 14: 318}
MAPS = {1: SUN, 2: PT, 14: HM14, 5: PM5, 7: PM7}
HOLES = {(1, 281), (2, 5)}
writes = []                    # registers die niet antwoorden (exception)
async def DEV(frame):
    slave, start, count = frame[0], int.from_bytes(frame[2:4], "big"), int.from_bytes(frame[4:6], "big")
    cb = subs["dr164/up"]
    class M: pass
    m = M()
    if slave not in MAPS:                               # slave 16 antwoordt niet -> time-out
        return
    if frame[1] == 6:                                   # FC06: register zetten en echo terugsturen
        MAPS[slave][start] = count; writes.append((slave, start, count)); m.payload = bytes(frame); cb(m); return
    if any((slave, a) in HOLES for a in range(start, start + count)):
        m.payload = bus.add_crc(bytes([slave, 0x83, 2]))
    else:
        w = b"".join(MAPS[slave].get(a, 0).to_bytes(2, "big") for a in range(start, start + count))
        m.payload = bus.add_crc(bytes([slave, 3, 2 * count]) + w)
    cb(m)

class St:
    def __init__(s, state, **attrs): s.state, s.attributes, s.last_updated = state, attrs, datetime.now(timezone.utc)
class States:
    def __init__(s): s.d = {}
    def get(s, e): return s.d.get(e)
class Hass:
    dead = set()
    def async_create_task(s, coro, name=None):
        assert asyncio.iscoroutine(coro), coro            # zoals HA: alleen coroutines
        return asyncio.ensure_future(coro)
    states = States(); config = types.SimpleNamespace(path=lambda p: "/tmp/dw_obs_test")
    def async_add_executor_job(s, f, *a):
        fut = asyncio.get_running_loop().create_future(); fut.set_result(f(*a)); return fut
    class services:
        calls = []
        @staticmethod
        def has_service(domain, svc): return (domain, svc) == ("tibber", "get_prices")
        @staticmethod
        async def async_call(domain, svc, data, blocking=False, return_response=False):
            Hass.services.calls.append((domain, svc, data))
            if (domain, svc) == ("tibber", "get_prices"):
                import datetime as _d
                h0 = time.time() - time.time() % 3600
                rows = [{"start_time": _d.datetime.fromtimestamp(h0 + i * 900).isoformat(),
                         "price": 0.20 if i < 4 else 0.50} for i in range(-8, 96)]
                return {"prices": {"Thuis": rows}}
            if (domain, svc) == ("climate", "set_temperature"):
                Hass.states.d[data["entity_id"]].attributes["temperature"] = data["temperature"]
            if (domain, svc) == ("number", "set_value"):
                if data["entity_id"] in Hass.dead:
                    raise HAErr("MAC_NO_ACK")
                Hass.states.d[data["entity_id"]].state = str(data["value"])
            if domain == "fan":
                st = Hass.states.d[data["entity_id"]]
                st.state = "on" if svc == "set_percentage" else "off"; st.attributes["percentage"] = data.get("percentage", 0)
class Entry:
    data = {"up_topic": "dr164/up", "down_topic": "dr164/down", "rooms": ["climate.a", "climate.b", "climate.woonkamer"],
            "outdoor_entity": "sensor.buiten", "price_entity": "sensor.prijs", "notify_service": "notify.mobile_app_test"}
    options = {}; entry_id = "abc"

async def main():
    h = Hass()
    h.states.d = {
        "climate.a": St("heat", friendly_name="Badkamer", current_temperature=19.4, temperature=20.5, valve_open_percent=55,
                        preset_temperatures={"comfort_temp": 20.5, "eco_temp": 19.0, "comfort_away_temp": 19.5, "eco_away_temp": 18.0}),
        "climate.b": St("heat", friendly_name="Finn", current_temperature=20.6, temperature=20.5, valve_open_percent=0,
                        preset_temperatures={"comfort_temp": 18.5, "eco_temp": 17.5}),
        "climate.woonkamer": St("off", friendly_name="Woonkamer", current_temperature=None, temperature=None, valve_open_percent=0),
        "sensor.buiten": St("1.5"), "sensor.prijs": St("0.23")}
    # kortere time-outs zodat de test snel loopt
    c = coord.DeWarmteCoordinator(h, Entry())
    c.bus = bus.ModbusBus(c._send, timeout=0.1, quiet=0.02, gap=0.0)
    await c.async_setup()
    data = None
    for i in range(3):
        data = await c._async_update_data()
        await asyncio.sleep(0)
    d, v, s = data["d"], data["v"], data["s"]
    assert v["t_supply"] == 23 and v["set_heating"] == 31 and v["power_mode"] == 0   # 30,25 + 0,75 preset-correctie; 1,5 °C = Normaal (3.5.5)
    assert s[16]["ok"] is False and s[1]["ok"] is True and d["blocks"] == []   # slave 16 stuk blokkeert niets
    assert (1, 281) not in [(k[0], k[1]) for k in c._raw]                    # gat in register blijft ontbreken
    assert d["outdoor_used"] == 1.5 and d["season_heating"] is True
    n = 0
    for desc in sens.SENSORS:
        val = desc.value_fn(data); n += 1
        if desc.attrs_fn: desc.attrs_fn(data)
        assert val is None or isinstance(val, (int, float, str, bool)), desc.key
    for desc in binm.BINARIES:
        assert desc.value_fn({**data, "c": c}) in (True, False, None), desc.key
    # schrijven: alleen toegestane registers, met echo bevestigd
    assert sorted(writes) == [(1, 769, 31), (1, 775, 0), (2, 6, 60)], writes           # goedkoopste uur: boiler naar 60
    assert c._raw[(1, 769)][0] == 31 and len(c.actions) >= 3 and all(a["ok"] for a in c.actions), c.actions
    # prijsplanner: nu goedkoop, straks duur -> voorverwarmen, kamerdoelen via climate.set_temperature
    assert c.planner.offset == 1.5 and d["feedforward"] == 0.75
    night = c.planner.block(time.time()) == "nacht"
    assert h.states.d["climate.a"].attributes["temperature"] == (19.0 if night else 20.5) + 1.5
    assert h.states.d["climate.b"].attributes["temperature"] == (17.5 if night else 18.5) + 1.5
    info = c.plan_info(); assert info["actief"] and len(info["planning"]) >= 20 and "climate.woonkamer" in info["kamers"]
    assert {(f[0], int.from_bytes(f[2:4], "big")) for f in published if f[1] == 6} <= set(load("writes").ALLOWED)
    assert all(f[1] in (3, 6) for f in published)
    # schakelaar uit -> geen writes meer
    await c.async_set_control(False, "test"); MAPS[1][769] = 25
    for _ in range(2): await c._async_update_data()
    assert len(writes) == 3
    lw = c.planner.last_written["climate.a"]; c.planner.last_written["climate.a"] = (lw[0], lw[1] - 300)
    h.states.d["climate.a"].attributes["temperature"] = 21.0                  # gebruiker past zelf aan
    c._last_plan = 0; await c._async_update_data()
    assert h.states.d["climate.a"].attributes["temperature"] == 21.0          # regeling uit: niets overschreven
    await c.async_set_control(True)
    c._last_plan = 0; await c._async_update_data()
    assert h.states.d["climate.a"].attributes["temperature"] == 21.0          # handmatige wijziging gerespecteerd
    assert "handmatig" in c.plan_rooms["climate.a"]["reden"]
    # vakantiemodus: alle kamers naar 17 °C (ook over handmatig heen), boiler 45 °C
    await c.async_set_vacation(True)
    c._last_plan = 0; dv = await c._async_update_data()
    assert h.states.d["climate.a"].attributes["temperature"] == 17.0
    assert h.states.d["climate.b"].attributes["temperature"] == 17.0
    assert dv["d"]["dhw_setpoint_advice"] == 45.0 and c.plan_info()["vakantiemodus"]
    await c.async_set_vacation_return(time.time() + 3 * 3600)            # binnen de opwarmtijd (6 u): weer normaal
    c._last_plan = 0; await c._async_update_data()
    assert not c.vacation_active(time.time()) and c.vacation_on
    assert h.states.d["climate.a"].attributes["temperature"] > 17.0
    await c.async_set_vacation_return(time.time() - 1)                   # terugkomstmoment voorbij: vanzelf uit
    await c._async_update_data()
    assert c.vacation_on is False and c.vacation_return is None
    # uurrapport
    assert timers and timers[0][1] == {"minute": 0, "second": 15}
    await timers[0][0]()
    rep = [x for x in notes if x[0] == "dewarmte_uurrapport"][-1]
    assert "aanvoersetpoint" in rep[2] and Hass.services.calls[-1][1] == "mobile_app_test", Hass.services.calls
    c.data = data; cops = [sens.DWSensorEntity(c, Entry(), d_) for d_ in sens.COP_SENSORS]
    assert len(cops) == 12 and cops[0]._attr_unique_id == "abc_cop_ao_week"
    for e_ in cops:
        e_.native_value; e_.extra_state_attributes                       # mag niet crashen
    assert c.cop.last.get("ao") is not None or c._last_values.get("ao_pm_energy") is None
    raw_s = [r for r in regs.RAW if r.bit is None or isinstance(r.bit, str)]; raw_b = [r for r in regs.RAW if isinstance(r.bit, int)]
    vals = data["v"]["raw"]
    assert vals["r1_80"] == 23 and vals["r1_0_12"] is True and vals["r2_53"] == 45
    print("PASS ha-glue:", n + len(sens.EXTRA), "hoofd-sensors +", len(raw_s), "register-sensors,", len(binm.BINARIES), "+", len(raw_b),
          "binaire sensors |", len(published), "frames, writes:", writes)
    print("     uurrapport:", rep[1]); print("     " + rep[2].replace("\n", "\n     "))

    # ---- servicemodus
    try:
        await c.async_service_write(1, 390, 15, "flow low"); assert False, "zonder servicemodus mag niets"
    except HAErr: pass
    c.set_service_mode(True); assert c.service_mode
    await c.async_service_write(1, 390, 15, "flow low")
    await c.async_service_write(1, 269, -30, "lagedruk")                # negatief -> two's complement
    assert (1, 390, 15) in writes and (1, 269, 0x10000 - 30) in writes
    try:
        await c.async_service_write(1, 390, 500, "flow low"); assert False, "buiten tabelgrenzen"
    except HAErr: pass
    try:
        await c.async_service_write(1, 816, 8, "force defrost"); assert False, "commandobits nooit"
    except HAErr: pass
    data = await c._async_update_data()
    assert data["v"]["raw"]["r1_269"] == -30 and data["v"]["raw"]["r1_390"] == 15
    assert os.path.exists("/tmp/dw_obs_test/servicelog.csv")
    c.service_until = time.monotonic() - 1; await c._async_update_data(); assert not c.service_mode

    # ---- watersysteem ontluchten: alleen 816 bit 4, lezen-aanpassen-schrijven
    SUN[816] = 0x0400                                       # bit 10 'allow backwater' staat aan
    try:
        await c.async_start_vent(); assert False, "zonder servicemodus mag niets"
    except HAErr: pass
    c.set_service_mode(True)
    n769 = sum(1 for w_ in writes if w_[:2] == (1, 769))
    await c.async_start_vent()
    assert writes[-1] == (1, 816, 0x0410) and c.vent, writes[-1]
    SUN[769] = 45                                           # regeling zou 769 willen corrigeren...
    await c._async_update_data(); assert c.vent["seen"]
    assert sum(1 for w_ in writes if w_[:2] == (1, 769)) == n769   # ...maar laat pomp AO met rust
    SUN[816] = 0x0400                                       # SunRain is klaar en zet de bit zelf terug
    await c._async_update_data(); assert c.vent is None and "klaar" in notes[-1][1], notes[-1]
    SUN[816] = 0x0400; await c.async_start_vent(); c.vent["start"] -= 31 * 60
    await c._async_update_data(); assert c.vent is None and writes[-1] == (1, 816, 0x0400)
    SUN[769] = 28; c.service_until = time.monotonic() - 1

    # ---- desinfectie (alleen warmtepomp)
    PT[10], PT[11] = 62, 20
    for st in c._sched.values(): st["next"] = 0.0          # instellingen direct opnieuw lezen
    await c._async_update_data()
    await c.async_start_disinfection()
    assert writes[-1] == (2, 6, 62) and c.disinfect["phase"] == "opwarmen", (writes[-3:], c.disinfect, c.actions[-1], c._last_values["raw"].get("r2_10"))
    PT[53] = 61; await c._async_update_data()
    assert c.disinfect["phase"] == "vasthouden" and "nog" in c.disinfect_text()
    c.disinfect["reached"] -= 21 * 60; await c._async_update_data()
    assert c.disinfect is None and writes[-1][:2] == (2, 6) and writes[-1][2] != 62
    assert any(n[0] == "dewarmte_desinfectie" and "geslaagd" in n[1] for n in notes)

    # ---- automatische desinfectie: 8 dagen niet heet -> start vanzelf (ook zonder goedkoopste moment)
    c.engine.last_hot = time.time() - 8.2 * 86400; PT[53] = 50
    c._last_plan = 0; await c._async_update_data()
    assert c.disinfect is not None and "automatisch" in c.actions[-1]["why"], c.actions[-1]
    await c.async_stop_disinfection()
    c._last_plan = 0; await c._async_update_data()
    assert c.disinfect is None                                                  # niet meteen opnieuw (max 1x per dag)

    # ---- meldingen, weekrapport, compressorstarts
    assert timers[1][1] == {"hour": 19, "minute": 0, "second": 30}
    c.alerts._since["modbus"] = time.monotonic() - 11 * 60
    st1 = c._sched[(1, 0, 15)]; ok_before = st1["ok"]; st1["ok"] = time.monotonic() - 3600
    ev = c.alerts.update(time.monotonic(), False, False, "", False, "", [])
    assert ev and "Geen verse data" in ev[0][1], ev
    st1["ok"] = ok_before
    await c.async_send_week_report(reset=False)
    wk = [x for x in notes if x[0] == "dewarmte_weekrapport"][-1]
    assert "tussenstand" in wk[1] and "Compressor:" in wk[2], wk
    assert c.last_week["titel"] and "kamers" in c.last_week
    print("     weekrapport:", wk[1]); print("     " + wk[2].replace("\n", "\n     "))

    # ---- oude MQTT-discovery opruimen (alleen dewarmte_* van de oude app)
    async def _clean():
        return await c.async_cleanup_old_discovery(wait=0.05)
    task = asyncio.ensure_future(_clean()); await asyncio.sleep(0.01)
    M = types.SimpleNamespace
    cb = subs["homeassistant/#"]
    cb(M(topic="homeassistant/sensor/dhw_2_22_16_x/config", retain=True,
         payload='{"unique_id": "dewarmte_dhw_2_22_16_x", "state_topic": "dewarmte/dhw_2/x/state", "availability_topic": "dewarmte/bridge/availability"}'))
    cb(M(topic="homeassistant/sensor/ander/config", retain=True, payload='{"unique_id": "iets_anders"}'))
    assert await task == 3
    assert sorted(t for t, p, r in retained if p == "" and r) == ["dewarmte/bridge/availability",
        "dewarmte/dhw_2/x/state", "homeassistant/sensor/dhw_2_22_16_x/config"], retained

    async def settle():
        if c._room_task: await c._room_task
    async def upd():
        r = await c._async_update_data(); await settle(); return r
    # ---- zelflerende kamerregeling (vervangt VTherm)
    h.states.d.update({
        "sensor.t_w": St("19.6"), "climate.trv_w": St("heat", temperature=20.5, current_temperature=21.0),
        "number.w_open": St("40"), "number.w_close": St("60"),
        "fan.jaga": St("off", percentage=0),
        "sensor.t_f": St("20.6"), "climate.trv_f": St("off", temperature=17.0),
        "number.f_open": St("100"), "number.f_close": St("0")})
    c.room_cfgs = rooms_m.parse_room_config(
        "climate.woonkamer | Woonkamer | sensor.t_w | climate.trv_w | number.w_open | number.w_close | 20,5 | 19 | fan.jaga\n"
        "climate.b | Finn | sensor.t_f | climate.trv_f | number.f_open | number.f_close | 19 | 18")
    c.rooms_ctl = rooms_m.RoomController(c.room_cfgs)
    c.planner.capped.add("climate.b")                                        # slaapkamer: maximum 20 °C
    ents = [clim.RoomThermostat(c, Entry(), x) for x in c.room_cfgs]
    assert ents[0]._attr_unique_id == "abc_room_woonkamer" and not ents[0].available
    h.states.d["climate.woonkamer"].attributes.pop("valve_open_percent", None)   # VTherm al uit
    c._last_room = 0; await upd()                           # uit: alleen meekijken
    assert not any(x[0] == "number" for x in Hass.services.calls)
    assert c.room_info["climate.woonkamer"]["valve"] == 40                   # klep uit opening/closing afgeleid
    MAPS[1][25] = 1 << 6                                                     # circulatiepomp AO draait
    await c.async_set_room_control(True)
    assert c.engine.offset == 0 and c.engine.trim == 0
    for st_ in c._sched.values(): st_["next"] = 0.0
    c._last_room = 0; await upd()
    calls = [x for x in Hass.services.calls if x[0] in ("number", "fan") or x[1] == "set_hvac_mode"]
    wo, wc = int(h.states.d["number.w_open"].state), int(h.states.d["number.w_close"].state)
    assert wo + wc == 100 and wo > 40, (wo, wc, c.room_info["climate.woonkamer"])   # 0,9 K te koud: verder open
    fo, fc = int(h.states.d["number.f_open"].state), int(h.states.d["number.f_close"].state)
    assert fo + fc == 100 and fo < 100, (fo, fc, c.room_info["climate.b"])
    assert ("climate", "set_hvac_mode", {"entity_id": "climate.trv_f", "hvac_mode": "heat"}) in Hass.services.calls
    assert h.states.d["fan.jaga"].state == "on" and 20 <= h.states.d["fan.jaga"].attributes["percentage"] <= 50, calls
    assert ents[0].available and ents[0].native_current_temperature == 19.6 and ents[0].hvac_action == "heating"
    assert ents[0].extra_state_attributes["valve_open_percent"] == wo
    assert c._room("climate.woonkamer").valve == wo
    tgt = c.room_info["climate.woonkamer"]["target"]                       # TRV-setpoint ruim boven doel
    assert ("climate", "set_temperature", {"entity_id": "climate.trv_w", "temperature": min(25.0, round((tgt + 4) * 2) / 2)}) \
        in Hass.services.calls, [x for x in Hass.services.calls if x[1] == "set_temperature"]
    # handmatig: doel tot het volgende blok, max. 3 uur
    await ents[1].async_set_temperature(temperature=21.0); await settle()
    assert ents[1].preset_mode == "handmatig" and ents[1].native_target_temperature == 20.0   # slaapkamer-maximum 20
    await ents[1].async_set_preset_mode("schema"); await settle(); assert ents[1].preset_mode == "schema"
    await ents[1].async_set_hvac_mode("off"); await settle()
    assert h.states.d["number.f_open"].state == "0" and ents[1].hvac_action == "off"
    # TRV die niet antwoordt: fout gelogd, regeling loopt door
    Hass.dead.add("number.w_open"); h.states.d["sensor.t_w"].state = "22.8"
    c._last_room = 0; await upd()
    assert c.rooms_ctl.state["climate.woonkamer"].trv_ok is False
    assert any(a_["name"] == "klep Woonkamer" and not a_["ok"] for a_ in c.actions)
    Hass.dead.clear()
    # uitzetten: TRV's krijgen hun eigen regeling terug
    await c.async_set_room_control(False)
    assert h.states.d["number.w_open"].state == "100" and h.states.d["number.w_close"].state == "0"
    assert h.states.d["fan.jaga"].state == "off"
    last = [x for x in Hass.services.calls if x[1] == "set_temperature" and x[2]["entity_id"] == "climate.trv_w"][-1]
    assert last[2]["temperature"] == c.room_info["climate.woonkamer"]["target"], last   # teruggeven: kamerdoel
    print("PASS kamerregeling:", {k: (i["valve"], i["target"], i["valve_reason"][:40]) for k, i in c.room_info.items()})

    # ---- uurrapport: telefoon alleen bij problemen
    n0 = sum(1 for x in Hass.services.calls if x[0] == "notify")
    await c.async_send_report()
    probs = c.last_report["problemen"]
    n1 = sum(1 for x in Hass.services.calls if x[0] == "notify")
    assert (n1 > n0) == bool(probs), (probs, n0, n1)
    c.report.sample_rooms({"k": {"name": "Woonkamer", "current": 17.0, "target": 18.5}})
    c.report.actions.append({"ok": False, "name": "klep Finn", "new": "0 %", "error": "MAC_NO_ACK", "time": "x", "old": "?"})
    probs = c.report.problems({}, True, 5, ["Finn"], 45)
    assert any("Woonkamer" in x for x in probs) and any("Pendelen" in x for x in probs), probs
    assert any("MAC_NO_ACK" in x for x in probs) and any("TRV Finn" in x for x in probs), probs
    print("PASS uurrapport:", probs)

    # ---- dashboard: elke verwijzing moet naar een echte entiteit wijzen
    ids = {("sensor", d.key) for d in sens.SENSORS + sens.EXTRA + sens.COP_SENSORS} | {("binary_sensor", d.key) for d in binm.BINARIES}
    ids |= {("sensor", x.key) for x in regs.RAW if not isinstance(x.bit, int)} | {("binary_sensor", x.key) for x in regs.RAW if isinstance(x.bit, int)}
    ids |= {("switch", "control"), ("switch", "service_mode"), ("switch", "plan"), ("switch", "vacation"), ("switch", "room_control"), ("datetime", "vacation_return"), ("button", "report_now"), ("button", "disinfect_start"), ("button", "disinfect_stop"), ("button", "week_now"), ("button", "vent_start"), ("button", "vent_stop")}
    ids |= {("number", f"n{k[0]}_{k[1]}") for k in load("writes").SERVICE}
    bad = []
    def resolve(platform, key):
        if (platform, key) not in ids: bad.append((platform, key))
        return f"{platform}.dw_{key}"
    board = dash.build(resolve, ["climate.kamer_1", "climate.kamer_2"])
    assert not bad, bad
    text = yaml.safe_dump(board, allow_unicode=True, sort_keys=False)
    assert yaml.safe_load(text) == board
    numbers = sum(len(cd["entities"]) for cd in board["views"][5]["cards"] if cd.get("type") == "entities")
    assert numbers == len(load("writes").SERVICE), (numbers, len(load("writes").SERVICE))
    open("/tmp/dw_dashboard.yaml", "w").write(text)
    print("PASS service/desinfectie/dashboard:", len(board["views"]), "views,", numbers, "service-instellingen,",
          len(text.splitlines()), "regels YAML")
    print("     bus:", {k: x["ok"] for k, x in s.items()}, "| voorgenomen:", d["summary"], "| blokkades:", d["blocks"])
    print("     obs-log:", os.listdir("/tmp/dw_obs_test"))
asyncio.run(main())
