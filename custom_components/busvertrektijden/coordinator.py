"""Shared data coordinator: one API call per stop per minute for all sensors."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .bus import Bus
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


def _hhmm_to_minutes(value: str | None) -> int | None:
    try:
        parts = str(value).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (TypeError, ValueError, IndexError):
        return None


class BusCoordinator(DataUpdateCoordinator[dict]):
    """Fetches departures for one stop."""

    def __init__(self, hass: HomeAssistant, bus: Bus) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {bus.stop_name}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.bus = bus

    async def _async_update_data(self) -> dict:
        try:
            data = await self.bus.fetch(async_get_clientsession(self.hass))
        except Exception as err:  # noqa: BLE001 - API errors of any kind
            raise UpdateFailed(f"Fout bij ophalen data: {err}") from err

        fetched = dt_util.utcnow()
        for stop in data["stops"]:
            expected = fetched + timedelta(seconds=int(stop.get("seconds") or 0))
            stop["expected_at"] = expected.isoformat()
            sched = _hhmm_to_minutes(stop.get("departure_time"))
            comp = _hhmm_to_minutes(stop.get("computed_time"))
            if sched is not None and comp is not None:
                diff = comp - sched
                if diff < -720:
                    diff += 1440
                elif diff > 720:
                    diff -= 1440
                stop["delay_minutes"] = diff
            else:
                stop["delay_minutes"] = 0
        data["fetched_at"] = fetched.isoformat()
        return data
