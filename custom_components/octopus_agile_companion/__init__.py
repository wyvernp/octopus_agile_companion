"""Octopus Agile Companion integration for Home Assistant."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, CONF_API_KEY, CONF_TARIFF_CODE, CONF_PRODUCT_CODE,
    CONF_CONSECUTIVE_PERIODS, CONF_FETCH_WINDOW_START, CONF_FETCH_WINDOW_END,
    CONF_CHEAP_THRESHOLD, CONF_EXPENSIVE_THRESHOLD,
    CONF_FLAT_RATE_COMPARISON, CONF_USAGE_PROFILE, CONF_DAILY_KWH,
    CONF_EXPORT_RATE, CONF_BATTERY_CAPACITY, CONF_ENABLE_CARBON,
    DATA_COORDINATOR, DEFAULT_CONSECUTIVE_PERIODS,
    DEFAULT_CHEAP_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD,
    DEFAULT_FLAT_RATE, DEFAULT_USAGE_PROFILE, DEFAULT_DAILY_KWH,
    DEFAULT_EXPORT_RATE, DEFAULT_BATTERY_CAPACITY, DEFAULT_ENABLE_CARBON,
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
    
    # Analytics options
    flat_rate = entry.options.get(CONF_FLAT_RATE_COMPARISON, DEFAULT_FLAT_RATE)
    usage_profile = entry.options.get(CONF_USAGE_PROFILE, DEFAULT_USAGE_PROFILE)
    daily_kwh = entry.options.get(CONF_DAILY_KWH, DEFAULT_DAILY_KWH)
    export_rate = entry.options.get(CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE)
    battery_capacity = entry.options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
    enable_carbon = entry.options.get(CONF_ENABLE_CARBON, DEFAULT_ENABLE_CARBON)

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
        CONF_FLAT_RATE_COMPARISON: flat_rate,
        CONF_USAGE_PROFILE: usage_profile,
        CONF_DAILY_KWH: daily_kwh,
        CONF_EXPORT_RATE: export_rate,
        CONF_BATTERY_CAPACITY: battery_capacity,
        CONF_ENABLE_CARBON: enable_carbon,
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
    
    def _get_entry_id(call_data: dict) -> str | None:
        """Get entry_id from call data or return first available."""
        if not hass.data.get(DOMAIN):
            return None
        return call_data.get("entry_id") or next(iter(hass.data[DOMAIN]), None)
    
    async def handle_get_rates(call: ServiceCall) -> ServiceResponse:
        """Handle get_rates service call."""
        entry_id = _get_entry_id(call.data)
        if not entry_id or entry_id not in hass.data[DOMAIN]:
            return {"error": "No integration instances configured"}
        
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
        entry_id = _get_entry_id(call.data)
        if not entry_id or entry_id not in hass.data[DOMAIN]:
            return {"error": "No integration instances configured"}
        
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
        entry_id = _get_entry_id(call.data)
        if not entry_id or entry_id not in hass.data[DOMAIN]:
            return {"error": "No integration instances configured"}
        
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

    # Analytics services
    async def handle_estimate_cost(call: ServiceCall) -> ServiceResponse:
        """Handle estimate_cost service call."""
        from .analytics import SavingsCalculator, UsagePatternAnalyzer
        
        entry_id = _get_entry_id(call.data)
        if not entry_id or entry_id not in hass.data[DOMAIN]:
            return {"error": "No integration instances configured"}
        
        coordinator = hass.data[DOMAIN][entry_id][DATA_COORDINATOR]
        daily_kwh = call.data.get("daily_kwh", 10.0)
        usage_profile = call.data.get("usage_profile", "working_family")
        flat_rate = call.data.get("flat_rate", 24.50)
        date_str = call.data.get("date")
        
        from datetime import datetime
        from zoneinfo import ZoneInfo
        LONDON_TZ = ZoneInfo("Europe/London")
        
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = datetime.now(LONDON_TZ).date()
        
        if target_date not in coordinator.rates_by_date:
            return {"error": f"No data for date {target_date}"}
        
        rates = coordinator.rates_by_date[target_date]
        calculator = SavingsCalculator(flat_rate)
        analyzer = UsagePatternAnalyzer(usage_profile)
        
        result = calculator.estimate_daily_cost(
            rates, analyzer.get_profile(), daily_kwh
        )
        result["date"] = str(target_date)
        result["usage_profile"] = usage_profile
        return result

    async def handle_suggest_load_time(call: ServiceCall) -> ServiceResponse:
        """Handle suggest_load_time service call."""
        from .analytics import UsagePatternAnalyzer
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        
        entry_id = _get_entry_id(call.data)
        if not entry_id or entry_id not in hass.data[DOMAIN]:
            return {"error": "No integration instances configured"}
        
        coordinator = hass.data[DOMAIN][entry_id][DATA_COORDINATOR]
        load_kwh = call.data.get("load_kwh", 1.0)
        duration_hours = call.data.get("duration_hours", 1.0)
        preferred_start = call.data.get("preferred_start")
        preferred_end = call.data.get("preferred_end")
        
        LONDON_TZ = ZoneInfo("Europe/London")
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        
        # Gather available future rates
        rates = []
        for day in [today, tomorrow]:
            if day in coordinator.rates_by_date:
                for slot in coordinator.rates_by_date[day]:
                    if slot["valid_from"] >= now_utc:
                        rates.append(slot)
        
        if not rates:
            return {"error": "No future rate data available"}
        
        analyzer = UsagePatternAnalyzer()
        result = analyzer.suggest_load_shift(
            rates, load_kwh, duration_hours, preferred_start, preferred_end
        )
        return result

    async def handle_analyze_export(call: ServiceCall) -> ServiceResponse:
        """Handle analyze_export service call for solar/battery users."""
        from .analytics import ExportOptimizer
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        entry_id = _get_entry_id(call.data)
        if not entry_id or entry_id not in hass.data[DOMAIN]:
            return {"error": "No integration instances configured"}
        
        coordinator = hass.data[DOMAIN][entry_id][DATA_COORDINATOR]
        export_rate = call.data.get("export_rate", 15.0)
        battery_capacity = call.data.get("battery_capacity", 10.0)
        date_str = call.data.get("date")
        
        LONDON_TZ = ZoneInfo("Europe/London")
        
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = datetime.now(LONDON_TZ).date()
        
        if target_date not in coordinator.rates_by_date:
            return {"error": f"No data for date {target_date}"}
        
        rates = coordinator.rates_by_date[target_date]
        optimizer = ExportOptimizer(
            export_rate=export_rate,
            battery_capacity_kwh=battery_capacity
        )
        
        result = optimizer.analyze_export_windows(rates)
        result["date"] = str(target_date)
        return result

    async def handle_get_carbon_intensity(call: ServiceCall) -> ServiceResponse:
        """Handle get_carbon_intensity service call."""
        from .analytics import CarbonIntensityAPI
        
        api = CarbonIntensityAPI()
        session = async_get_clientsession(hass)
        
        forecast = call.data.get("forecast", False)
        hours = call.data.get("hours", 24)
        postcode = call.data.get("postcode")
        
        if postcode:
            data = await api.fetch_regional(session, postcode)
            if data:
                return {
                    "current": {
                        "intensity": data.intensity,
                        "index": data.index,
                        "from": data.from_time.isoformat(),
                        "to": data.to_time.isoformat(),
                    },
                    "regional": True,
                    "postcode": postcode,
                }
        
        if forecast:
            forecast_data = await api.fetch_forecast(session, hours)
            return {
                "forecast": [
                    {
                        "intensity": d.intensity,
                        "index": d.index,
                        "from": d.from_time.isoformat(),
                        "to": d.to_time.isoformat(),
                    }
                    for d in forecast_data
                ],
                "count": len(forecast_data),
            }
        else:
            data = await api.fetch_current(session)
            if data:
                return {
                    "current": {
                        "intensity": data.intensity,
                        "index": data.index,
                        "from": data.from_time.isoformat(),
                        "to": data.to_time.isoformat(),
                    }
                }
            return {"error": "Failed to fetch carbon intensity"}

    # Register analytics services
    if not hass.services.has_service(DOMAIN, "estimate_cost"):
        hass.services.async_register(
            DOMAIN,
            "estimate_cost",
            handle_estimate_cost,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("date"): cv.string,
                vol.Optional("daily_kwh", default=10.0): vol.Coerce(float),
                vol.Optional("usage_profile", default="working_family"): cv.string,
                vol.Optional("flat_rate", default=24.50): vol.Coerce(float),
            }),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, "suggest_load_time"):
        hass.services.async_register(
            DOMAIN,
            "suggest_load_time",
            handle_suggest_load_time,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("load_kwh", default=1.0): vol.Coerce(float),
                vol.Optional("duration_hours", default=1.0): vol.Coerce(float),
                vol.Optional("preferred_start"): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=23)
                ),
                vol.Optional("preferred_end"): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=23)
                ),
            }),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, "analyze_export"):
        hass.services.async_register(
            DOMAIN,
            "analyze_export",
            handle_analyze_export,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("date"): cv.string,
                vol.Optional("export_rate", default=15.0): vol.Coerce(float),
                vol.Optional("battery_capacity", default=10.0): vol.Coerce(float),
            }),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, "get_carbon_intensity"):
        hass.services.async_register(
            DOMAIN,
            "get_carbon_intensity",
            handle_get_carbon_intensity,
            schema=vol.Schema({
                vol.Optional("forecast", default=False): cv.boolean,
                vol.Optional("hours", default=24): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=48)
                ),
                vol.Optional("postcode"): cv.string,
            }),
            supports_response=SupportsResponse.ONLY,
        )
