from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import (
    DOMAIN, CONF_API_KEY, CONF_TARIFF_CODE, CONF_PRODUCT_CODE,
    CONF_CONSECUTIVE_PERIODS, CONF_FETCH_WINDOW_START, CONF_FETCH_WINDOW_END,
    DATA_COORDINATOR, DEFAULT_CONSECUTIVE_PERIODS
)
from .coordinator import OctopusAgileCoordinator
from .api import OctopusAgileAPI

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Octopus Agile Companion integration."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    api_key = entry.data[CONF_API_KEY]
    product_code = entry.data[CONF_PRODUCT_CODE]
    tariff_code = entry.data[CONF_TARIFF_CODE]
    fetch_window_start = entry.data.get(CONF_FETCH_WINDOW_START)
    fetch_window_end = entry.data.get(CONF_FETCH_WINDOW_END)
    periods = entry.options.get(CONF_CONSECUTIVE_PERIODS, DEFAULT_CONSECUTIVE_PERIODS)

    api = OctopusAgileAPI(api_key, product_code, tariff_code)
    coordinator = OctopusAgileCoordinator(hass, api, fetch_window_start, fetch_window_end)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        CONF_CONSECUTIVE_PERIODS: periods,
    }

    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    await hass.config_entries.async_forward_entry_setup(entry, "binary_sensor")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
