from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FILTERS,
    CONF_STOP_NAME,
    DEFAULT_FILTER_COUNT,
    DOMAIN,
    STOP_SENSOR_DEPARTURES,
    TICK_INTERVAL,
)
from .coordinator import BusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator: BusCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        StopSensor(coordinator, entry),
        DepartureMinutesSensor(coordinator, entry, None),
        DepartureTimeSensor(coordinator, entry, None),
    ]
    for flt in entry.options.get(CONF_FILTERS, []):
        entities.append(DepartureMinutesSensor(coordinator, entry, flt))
        entities.append(DepartureTimeSensor(coordinator, entry, flt))
    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data[CONF_STOP_NAME],
        manufacturer="busvertrektijden.nl",
        model="Bushalte",
        entry_type=DeviceEntryType.SERVICE,
    )


class StopSensor(CoordinatorEntity[BusCoordinator], SensorEntity):
    """The original v2 sensor: seconds until the first departure + all details as attributes.

    Name, unique_id, state and attributes are kept compatible with v2 so existing
    dashboards, cards and automations keep working.
    """

    _attr_icon = "mdi:bus-stop"

    def __init__(self, coordinator: BusCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._stop = entry.data[CONF_STOP_NAME]
        self._attr_name = f"Bushalte {self._stop}"
        self._attr_unique_id = self._stop
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        stops = (self.coordinator.data or {}).get("stops") or []
        return stops[0]["seconds"] if stops else 0

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "alerts": data.get("alerts", []),
            "stops": (data.get("stops") or [])[:STOP_SENSOR_DEPARTURES],
            "fetched_at": data.get("fetched_at"),
        }


class _DepartureBase(CoordinatorEntity[BusCoordinator], SensorEntity):
    """Next departure for the whole stop (flt=None) or for one line/direction filter."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BusCoordinator, entry: ConfigEntry, flt: dict | None) -> None:
        super().__init__(coordinator)
        self._stop = entry.data[CONF_STOP_NAME]
        self._flt = flt
        self._lines = {str(x).strip().lower() for x in (flt or {}).get("lines", []) if str(x).strip()}
        self._dirs = {str(x).strip().lower() for x in (flt or {}).get("directions", []) if str(x).strip()}
        self._count = int((flt or {}).get("count", DEFAULT_FILTER_COUNT))
        self._attr_device_info = _device_info(entry)
        if flt:
            self._attr_translation_placeholders = {"filter": flt["name"]}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Count down locally between API calls
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=TICK_INTERVAL))
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    def _matches(self, stop: dict) -> bool:
        if self._lines and str(stop.get("bus_number", "")).strip().lower() not in self._lines:
            return False
        if self._dirs and str(stop.get("name", "")).strip().lower() not in self._dirs:
            return False
        return True

    def _departures(self) -> list[dict]:
        """Matching departures that have not left yet, soonest first (cancelled included)."""
        now = dt_util.utcnow()
        out = []
        for stop in (self.coordinator.data or {}).get("stops") or []:
            if not self._matches(stop):
                continue
            exp = dt_util.parse_datetime(stop.get("expected_at") or "")
            if exp is None or exp < now - timedelta(seconds=30):
                continue
            out.append((exp, stop))
        out.sort(key=lambda x: x[0])
        return [dict(s, _exp=e) for e, s in out]

    def _next(self) -> dict | None:
        return next((d for d in self._departures() if not d.get("cancelled")), None)

    @staticmethod
    def _minutes(exp: datetime) -> int:
        return max(0, math.floor((exp - dt_util.utcnow()).total_seconds() / 60))

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self):
        deps = self._departures()
        nxt = next((d for d in deps if not d.get("cancelled")), None)
        alerts = list((self.coordinator.data or {}).get("alerts") or [])
        attrs = {
            "stop": self._stop,
            "lines": sorted(self._lines) if self._lines else None,
            "directions": sorted(self._dirs) if self._dirs else None,
            "line": nxt.get("bus_number") if nxt else None,
            "direction": nxt.get("name") if nxt else None,
            "trip_name": nxt.get("trip_name") if nxt else None,
            "scheduled_time": (nxt.get("departure_time") or "")[:5] if nxt else None,
            "expected_time": nxt.get("computed_time") if nxt else None,
            "delay_minutes": nxt.get("delay_minutes") if nxt else None,
            "next_departures": [
                {
                    "line": d.get("bus_number"),
                    "direction": d.get("name"),
                    "minutes": self._minutes(d["_exp"]),
                    "time": d.get("computed_time"),
                    "scheduled_time": (d.get("departure_time") or "")[:5],
                    "delay_minutes": d.get("delay_minutes"),
                    "cancelled": bool(d.get("cancelled")),
                    "trip_name": d.get("trip_name"),
                }
                for d in deps[: self._count]
            ],
            "alerts": alerts + sorted({a for d in deps[: self._count] for a in (d.get("alerts") or [])}),
        }
        return attrs


class DepartureMinutesSensor(_DepartureBase):
    """Minutes until the next (non-cancelled) departure."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator, entry, flt) -> None:
        super().__init__(coordinator, entry, flt)
        stop = entry.data[CONF_STOP_NAME]
        if flt:
            self._attr_translation_key = "filter_minutes"
            self._attr_unique_id = f"{stop}_{flt['id']}_minutes"
        else:
            self._attr_translation_key = "next_minutes"
            self._attr_unique_id = f"{stop}_next_minutes"

    @property
    def native_value(self):
        nxt = self._next()
        return self._minutes(nxt["_exp"]) if nxt else None


class DepartureTimeSensor(_DepartureBase):
    """Expected time of the next (non-cancelled) departure."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, entry, flt) -> None:
        super().__init__(coordinator, entry, flt)
        stop = entry.data[CONF_STOP_NAME]
        if flt:
            self._attr_translation_key = "filter_time"
            self._attr_unique_id = f"{stop}_{flt['id']}_time"
        else:
            self._attr_translation_key = "next_time"
            self._attr_unique_id = f"{stop}_next_time"

    @property
    def native_value(self):
        nxt = self._next()
        return (nxt["_exp"] + timedelta(seconds=30)).replace(second=0, microsecond=0) if nxt else None
