"""Number platform for Octopus Agile Companion."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    CONF_CHEAP_THRESHOLD,
    CONF_EXPENSIVE_THRESHOLD,
    ATTRIBUTION,
    DEFAULT_CHEAP_THRESHOLD,
    DEFAULT_EXPENSIVE_THRESHOLD,
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Octopus Agile number entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[DATA_COORDINATOR]
    device_info = data["device_info"]

    entities = [
        CheapThresholdNumber(coordinator, entry, device_info),
        ExpensiveThresholdNumber(coordinator, entry, device_info),
    ]

    async_add_entities(entities, True)


class OctopusAgileBaseNumber(CoordinatorEntity, NumberEntity):
    """Base class for Octopus Agile number entities."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "p/kWh"

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = device_info


class CheapThresholdNumber(OctopusAgileBaseNumber):
    """Number entity for setting the cheap rate threshold."""

    _attr_icon = "mdi:tag-arrow-down"
    _attr_native_min_value = -50
    _attr_native_max_value = 100
    _attr_native_step = 0.5

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the number entity."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_cheap_threshold"
        # Get initial value from options
        self._value = entry.options.get(CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Cheap rate threshold"

    @property
    def native_value(self) -> float:
        """Return the current threshold value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set the threshold value."""
        self._value = value
        # Update the hass.data so binary sensors can use it
        self.hass.data[DOMAIN][self._entry.entry_id][CONF_CHEAP_THRESHOLD] = value
        self.async_write_ha_state()


class ExpensiveThresholdNumber(OctopusAgileBaseNumber):
    """Number entity for setting the expensive rate threshold."""

    _attr_icon = "mdi:tag-arrow-up"
    _attr_native_min_value = 0
    _attr_native_max_value = 200
    _attr_native_step = 0.5

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the number entity."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_expensive_threshold"
        # Get initial value from options
        self._value = entry.options.get(CONF_EXPENSIVE_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Expensive rate threshold"

    @property
    def native_value(self) -> float:
        """Return the current threshold value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set the threshold value."""
        self._value = value
        # Update the hass.data so binary sensors can use it
        self.hass.data[DOMAIN][self._entry.entry_id][CONF_EXPENSIVE_THRESHOLD] = value
        self.async_write_ha_state()
