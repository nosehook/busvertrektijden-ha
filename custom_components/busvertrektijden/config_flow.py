from __future__ import annotations

import re

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from .const import (
    DOMAIN,
    CONF_STOP_NAME,
    CONF_SHORT_NAME_FILTER,
    CONF_FILTERS,
    API_URL,
    DEFAULT_FILTER_COUNT,
)
import voluptuous as vol
import aiohttp


def normalize_commas(value: str | None) -> str | None:
    if value is None:
        return None
    return ",".join(part.strip() for part in value.strip().split(","))


class BusVertrektijdenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Bus vertrektijden config flow."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BusVertrektijdenOptionsFlow()

    def __init__(self):
        self._search_query: str | None = None
        self._stops: dict[str] | None = None
        self._selected_stop: str | None = None
        self._short_name_filter: str | None = None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self._search_query = user_input['search']
            await self._get_stops()
            if self._stops and len(self._stops) > 1:
                return await self.async_step_select_stop()
            else:
                errors['search'] = "Halte niet gevonden. Probeer opnieuw."

        SEARCH_SCHEMA = vol.Schema({
            vol.Required('search'): str
        })

        return self.async_show_form(
            step_id="user",
            data_schema=SEARCH_SCHEMA,
            errors=errors
        )

    async def _get_stops(self):
        """Fetch stops from the API."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/stops?search={self._search_query}") as response:
                data = await response.json()
                stopTimes = dict({"redo": "-- Zoek opnieuw --"})
                for item in data['result']:
                    name = item['stop_name']
                    stopTimes[name] = name
                self._stops = stopTimes

    async def async_step_select_stop(self, user_input=None):
        """Final step: user selects a stop from the list."""

        if user_input is None:
            return self.async_show_form(
                step_id="select_stop",
                data_schema=vol.Schema({
                    vol.Required("selected_stop"): vol.In(self._stops)
                })
            )

        selected_stop = user_input["selected_stop"]
        if selected_stop == "redo":
            return await self.async_step_user()
        else:
            self._selected_stop = selected_stop
            return await self.async_step_filters()

    async def async_step_filters(self, user_input=None):
        """Optional step: user sets filters for short name"""
        if user_input is None:
            return self.async_show_form(
                step_id="filters",
                data_schema=vol.Schema({
                    vol.Optional("short_name_filter"): str
                })
            )

        self._short_name_filter = normalize_commas(
            user_input.get("short_name_filter"))
        return self.async_create_entry(
            title=self._selected_stop,
            data={CONF_STOP_NAME: self._selected_stop, CONF_SHORT_NAME_FILTER: self._short_name_filter})


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "filter"


def _natural_key(value: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", str(value))]


class BusVertrektijdenOptionsFlow(config_entries.OptionsFlow):
    """Options: add or remove line/direction filters for this stop."""

    def __init__(self) -> None:
        self._new: dict = {}

    def _stops(self) -> list[dict]:
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        return list(((coordinator.data or {}) if coordinator else {}).get("stops") or [])

    def _filters(self) -> list[dict]:
        return list(self.config_entry.options.get(CONF_FILTERS, []))

    async def async_step_init(self, user_input=None):
        menu = ["add_filter"]
        if self._filters():
            menu.append("remove_filter")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_filter(self, user_input=None):
        errors = {}
        if user_input is not None:
            lines = [str(x).strip() for x in user_input.get("lines", []) if str(x).strip()]
            if not lines:
                errors["lines"] = "no_lines"
            else:
                self._new = {
                    "lines": lines,
                    "name": (user_input.get("name") or "").strip(),
                    "count": int(user_input.get("count", DEFAULT_FILTER_COUNT)),
                }
                return await self.async_step_add_filter_directions()

        lines = sorted({str(s.get("bus_number")) for s in self._stops() if s.get("bus_number")}, key=_natural_key)
        schema = vol.Schema({
            vol.Required("lines", default=[]): SelectSelector(SelectSelectorConfig(
                options=lines, multiple=True, custom_value=True, mode=SelectSelectorMode.LIST)),
            vol.Optional("name"): TextSelector(),
            vol.Optional("count", default=DEFAULT_FILTER_COUNT): NumberSelector(NumberSelectorConfig(
                min=1, max=10, step=1, mode=NumberSelectorMode.SLIDER)),
        })
        return self.async_show_form(step_id="add_filter", data_schema=schema, errors=errors,
                                    description_placeholders={"stop": self.config_entry.title})

    async def async_step_add_filter_directions(self, user_input=None):
        if user_input is not None:
            dirs = [str(x).strip() for x in user_input.get("directions", []) if str(x).strip()]
            lines = self._new["lines"]
            name = self._new["name"] or (" + ".join(lines) + (f" naar {' / '.join(dirs)}" if dirs else ""))
            existing = {f["id"] for f in self._filters()}
            fid, n = _slug(name), 2
            while fid in existing:
                fid, n = f"{_slug(name)}_{n}", n + 1
            flt = {"id": fid, "name": name, "lines": lines, "directions": dirs, "count": self._new["count"]}
            return self.async_create_entry(data={**self.config_entry.options, CONF_FILTERS: self._filters() + [flt]})

        wanted = {l.lower() for l in self._new["lines"]}
        dirs = sorted({str(s.get("name")) for s in self._stops()
                       if s.get("name") and str(s.get("bus_number", "")).lower() in wanted})
        schema = vol.Schema({
            vol.Optional("directions", default=[]): SelectSelector(SelectSelectorConfig(
                options=dirs, multiple=True, custom_value=True, mode=SelectSelectorMode.LIST)),
        })
        return self.async_show_form(step_id="add_filter_directions", data_schema=schema,
                                    description_placeholders={"lines": ", ".join(self._new["lines"])})

    async def async_step_remove_filter(self, user_input=None):
        filters = self._filters()
        if user_input is not None:
            remove = set(user_input.get("filters", []))
            keep = [f for f in filters if f["id"] not in remove]
            return self.async_create_entry(data={**self.config_entry.options, CONF_FILTERS: keep})
        schema = vol.Schema({
            vol.Required("filters", default=[]): SelectSelector(SelectSelectorConfig(
                options=[SelectOptionDict(value=f["id"], label=f["name"]) for f in filters],
                multiple=True, mode=SelectSelectorMode.LIST)),
        })
        return self.async_show_form(step_id="remove_filter", data_schema=schema)
