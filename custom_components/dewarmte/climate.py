"""DeWarmte-thermostaat per kamer (zelflerende kamerregeling, vervangt Versatile Thermostat)."""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .sensor import main_device

PRESET_AUTO = "schema"
PRESET_MANUAL = "handmatig"


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RoomThermostat(c, entry, cfg) for cfg in c.room_cfgs])


def _slug(key: str) -> str:
    return key.split(".", 1)[-1]


class RoomThermostat(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:home-thermometer"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_AUTO, PRESET_MANUAL]
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _attr_min_temp = 7.0
    _attr_max_temp = 25.0
    _attr_target_temperature_step = 0.5
    _enable_turn_on_off_backwards_compatibility = False
    _unrecorded_attributes = frozenset({"model", "klep_reden", "doel_reden", "klep_gewenst"})

    def __init__(self, coordinator, entry, cfg) -> None:
        super().__init__(coordinator)
        self.cfg = cfg
        self._attr_name = cfg.name
        self._attr_unique_id = f"{entry.entry_id}_room_{_slug(cfg.key)}"
        self._attr_device_info = main_device(entry)

    @property
    def _i(self) -> dict:
        return self.coordinator.room_info.get(self.cfg.key) or {}

    @property
    def available(self) -> bool:
        return self.coordinator.room_control

    @property
    def native_current_temperature(self):
        return self._i.get("current")

    @property
    def native_target_temperature(self):
        return self._i.get("target")

    @property
    def hvac_mode(self):
        return HVACMode.OFF if self._i.get("mode") == "off" else HVACMode.HEAT

    @property
    def hvac_action(self):
        i = self._i
        if i.get("mode") == "off":
            return HVACAction.OFF
        return HVACAction.HEATING if i.get("heating") else HVACAction.IDLE

    @property
    def preset_mode(self):
        return PRESET_MANUAL if self._i.get("manual") else PRESET_AUTO

    @property
    def extra_state_attributes(self):
        i = self._i
        return {"valve_open_percent": i.get("valve"), "klep_gewenst": i.get("valve_want"),
                "klep_reden": i.get("valve_reason"), "doel_reden": i.get("target_reason"),
                "fan_percentage": i.get("fan"), "raam_open": i.get("window"), "window_state": "on" if i.get("window") else "off",
                "trv_bevestigd": i.get("trv_ok"), "dag": self.cfg.day, "nacht": self.cfg.night,
                "model": i.get("model")}

    async def async_set_temperature(self, **kwargs) -> None:
        if ATTR_TEMPERATURE in kwargs:
            await self.coordinator.async_room_set_temperature(self.cfg.key, float(kwargs[ATTR_TEMPERATURE]))
        if kwargs.get("hvac_mode"):
            await self.async_set_hvac_mode(kwargs["hvac_mode"])

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        await self.coordinator.async_room_set_mode(self.cfg.key, "off" if hvac_mode == HVACMode.OFF else "heat")

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_AUTO:
            await self.coordinator.async_room_auto(self.cfg.key)
        else:
            t = self._i.get("target")
            if t is not None:
                await self.coordinator.async_room_set_temperature(self.cfg.key, t)
