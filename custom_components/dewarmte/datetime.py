"""Datum/tijd 'Vakantie: terug op': vanaf zoveel uur ervoor wordt huis en boiler weer opgewarmd."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .sensor import main_device


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VacationReturn(c, entry)])


class VacationReturn(CoordinatorEntity, DateTimeEntity):
    _attr_has_entity_name = True
    _attr_name = "Vakantie terug op"
    _attr_icon = "mdi:airplane-landing"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_vacation_return"
        self._attr_device_info = main_device(entry)

    @property
    def native_value(self) -> datetime | None:
        ts = self.coordinator.vacation_return
        return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_vacation_return(value.timestamp())
