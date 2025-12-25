"""Octopus Agile Companion integration for Home Assistant."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (
    DOMAIN, CONF_API_KEY, CONF_TARIFF_CODE, CONF_PRODUCT_CODE,
    CONF_CONSECUTIVE_PERIODS, CONF_FETCH_WINDOW_START, CONF_FETCH_WINDOW_END,
    CONF_CHEAP_THRESHOLD, CONF_EXPENSIVE_THRESHOLD,
    DATA_COORDINATOR, DEFAULT_CONSECUTIVE_PERIODS,
    DEFAULT_CHEAP_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD,
)
from .coordinator import OctopusAgileCoordinator
from .api import OctopusAgileAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Octopus Agile Companion integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Octopus Agile Companion from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    product_code = entry.data[CONF_PRODUCT_CODE]
    tariff_code = entry.data[CONF_TARIFF_CODE]
    fetch_window_start = entry.data.get(CONF_FETCH_WINDOW_START)
    fetch_window_end = entry.data.get(CONF_FETCH_WINDOW_END)
    
    # Get options with fallbacks to defaults
    periods = entry.options.get(CONF_CONSECUTIVE_PERIODS, DEFAULT_CONSECUTIVE_PERIODS)
    cheap_threshold = entry.options.get(CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD)
    expensive_threshold = entry.options.get(CONF_EXPENSIVE_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD)

    # Create device info for all entities to share
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Octopus Agile",
        manufacturer="Octopus Energy",
        model=product_code,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://octopus.energy/dashboard/developer/",
    )

    api = OctopusAgileAPI(api_key, product_code, tariff_code)
    coordinator = OctopusAgileCoordinator(
        hass, api, fetch_window_start, fetch_window_end, entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        CONF_CONSECUTIVE_PERIODS: periods,
        CONF_CHEAP_THRESHOLD: cheap_threshold,
        CONF_EXPENSIVE_THRESHOLD: expensive_threshold,
        "device_info": device_info,
        "tariff_code": tariff_code,
    }

    # Register services
    await async_setup_services(hass, entry)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    return True


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("Options updated, reloading integration")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry):
    """Set up services for the integration."""
    
    async def handle_get_rates(call: ServiceCall) -> ServiceResponse:
        """Handle get_rates service call."""
        entry_id = call.data.get("entry_id") or list(hass.data[DOMAIN].keys())[0]
        if entry_id not in hass.data[DOMAIN]:
            return {"error": "Integration not found"}
        
        coordinator = hass.data[DOMAIN][entry_id][DATA_COORDINATOR]
        date_str = call.data.get("date")
        
        from datetime import datetime
        from zoneinfo import ZoneInfo
        LONDON_TZ = ZoneInfo("Europe/London")
        
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = datetime.now(LONDON_TZ).date()
        
        if target_date not in coordinator.rates_by_date:
            return {"rates": [], "date": str(target_date), "error": "No data for date"}
        
        rates = coordinator.rates_by_date[target_date]
        return {
            "date": str(target_date),
            "rates": [
                {
                    "valid_from": slot["valid_from"].isoformat(),
                    "valid_to": slot["valid_to"].isoformat(),
                    "value_inc_vat": slot["value_inc_vat"],
                }
                for slot in rates
            ],
            "average": sum(s["value_inc_vat"] for s in rates) / len(rates) if rates else None,
            "min": min(s["value_inc_vat"] for s in rates) if rates else None,
            "max": max(s["value_inc_vat"] for s in rates) if rates else None,
        }
    
    async def handle_get_cheapest_slots(call: ServiceCall) -> ServiceResponse:
        """Handle get_cheapest_slots service call."""
        entry_id = call.data.get("entry_id") or list(hass.data[DOMAIN].keys())[0]
        if entry_id not in hass.data[DOMAIN]:
            return {"error": "Integration not found"}
        
        coordinator = hass.data[DOMAIN][entry_id][DATA_COORDINATOR]
        num_slots = call.data.get("num_slots", 1)
        date_str = call.data.get("date")
        consecutive = call.data.get("consecutive", False)
        
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        LONDON_TZ = ZoneInfo("Europe/London")
        
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = datetime.now(LONDON_TZ).date()
        
        if target_date not in coordinator.rates_by_date:
            return {"slots": [], "date": str(target_date), "error": "No data for date"}
        
        rates = coordinator.rates_by_date[target_date]
        
        if consecutive:
            # Find cheapest consecutive window
            if num_slots > len(rates):
                return {"slots": [], "error": "Not enough slots available"}
            
            best_start = 0
            best_cost = float("inf")
            for i in range(len(rates) - num_slots + 1):
                window_cost = sum(rates[j]["value_inc_vat"] for j in range(i, i + num_slots))
                if window_cost < best_cost:
                    best_cost = window_cost
                    best_start = i
            
            cheapest = rates[best_start:best_start + num_slots]
        else:
            # Find N cheapest individual slots
            sorted_rates = sorted(rates, key=lambda x: x["value_inc_vat"])
            cheapest = sorted_rates[:num_slots]
            # Sort by time for output
            cheapest = sorted(cheapest, key=lambda x: x["valid_from"])
        
        return {
            "date": str(target_date),
            "slots": [
                {
                    "valid_from": slot["valid_from"].isoformat(),
                    "valid_to": slot["valid_to"].isoformat(),
                    "value_inc_vat": slot["value_inc_vat"],
                }
                for slot in cheapest
            ],
            "total_cost": sum(s["value_inc_vat"] for s in cheapest),
            "average_cost": sum(s["value_inc_vat"] for s in cheapest) / len(cheapest) if cheapest else None,
        }

    async def handle_get_expensive_slots(call: ServiceCall) -> ServiceResponse:
        """Handle get_expensive_slots service call."""
        entry_id = call.data.get("entry_id") or list(hass.data[DOMAIN].keys())[0]
        if entry_id not in hass.data[DOMAIN]:
            return {"error": "Integration not found"}
        
        coordinator = hass.data[DOMAIN][entry_id][DATA_COORDINATOR]
        num_slots = call.data.get("num_slots", 1)
        date_str = call.data.get("date")
        
        from datetime import datetime
        from zoneinfo import ZoneInfo
        LONDON_TZ = ZoneInfo("Europe/London")
        
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = datetime.now(LONDON_TZ).date()
        
        if target_date not in coordinator.rates_by_date:
            return {"slots": [], "date": str(target_date), "error": "No data for date"}
        
        rates = coordinator.rates_by_date[target_date]
        sorted_rates = sorted(rates, key=lambda x: x["value_inc_vat"], reverse=True)
        expensive = sorted_rates[:num_slots]
        expensive = sorted(expensive, key=lambda x: x["valid_from"])
        
        return {
            "date": str(target_date),
            "slots": [
                {
                    "valid_from": slot["valid_from"].isoformat(),
                    "valid_to": slot["valid_to"].isoformat(),
                    "value_inc_vat": slot["value_inc_vat"],
                }
                for slot in expensive
            ],
            "total_cost": sum(s["value_inc_vat"] for s in expensive),
            "average_cost": sum(s["value_inc_vat"] for s in expensive) / len(expensive) if expensive else None,
        }

    # Register services only once
    if not hass.services.has_service(DOMAIN, "get_rates"):
        hass.services.async_register(
            DOMAIN,
            "get_rates",
            handle_get_rates,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("date"): cv.string,
            }),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, "get_cheapest_slots"):
        hass.services.async_register(
            DOMAIN,
            "get_cheapest_slots",
            handle_get_cheapest_slots,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("date"): cv.string,
                vol.Optional("num_slots", default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=48)
                ),
                vol.Optional("consecutive", default=False): cv.boolean,
            }),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, "get_expensive_slots"):
        hass.services.async_register(
            DOMAIN,
            "get_expensive_slots",
            handle_get_expensive_slots,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("date"): cv.string,
                vol.Optional("num_slots", default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=48)
                ),
            }),
            supports_response=SupportsResponse.ONLY,
        )
