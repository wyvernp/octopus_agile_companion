"""Sensor platform for Octopus Agile Companion."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    CONF_CONSECUTIVE_PERIODS,
    CONF_CHEAP_THRESHOLD,
    CONF_EXPENSIVE_THRESHOLD,
    ATTRIBUTION,
)

LONDON_TZ = ZoneInfo("Europe/London")


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Octopus Agile sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[DATA_COORDINATOR]
    periods = data[CONF_CONSECUTIVE_PERIODS]
    device_info = data["device_info"]

    entities = [
        # Current rate sensor with rich attributes
        CurrentRateSensor(coordinator, entry, device_info),
        # Next rate sensor
        NextRateSensor(coordinator, entry, device_info),
        # Daily statistics sensors
        TodayAverageRateSensor(coordinator, entry, device_info),
        TodayMinRateSensor(coordinator, entry, device_info),
        TodayMaxRateSensor(coordinator, entry, device_info),
        TomorrowAverageRateSensor(coordinator, entry, device_info),
    ]

    # Add cheapest window sensors for each period
    for p in periods:
        entities.append(TodayCheapestWindowSensor(coordinator, entry, p, device_info))
        entities.append(TomorrowCheapestWindowSensor(coordinator, entry, p, device_info))
        entities.append(TodayCheapestWindowCostSensor(coordinator, entry, p, device_info))

    async_add_entities(entities, True)


class OctopusAgileBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Octopus Agile sensors."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = device_info


class CurrentRateSensor(OctopusAgileBaseSensor):
    """Sensor showing the current electricity rate."""

    _attr_icon = "mdi:currency-gbp"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_current_rate"
        self._attr_translation_key = "current_rate"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Current rate"

    @property
    def native_value(self):
        """Return the current rate."""
        current = self.coordinator.get_current_rate()
        return round(current["value_inc_vat"], 2) if current else None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = {}
        current = self.coordinator.get_current_rate()
        if current:
            attrs["valid_from"] = current["valid_from"].isoformat()
            attrs["valid_to"] = current["valid_to"].isoformat()
            attrs["minutes_remaining"] = max(
                0,
                int(
                    (
                        current["valid_to"]
                        - datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
                    ).total_seconds()
                    / 60
                ),
            )

        next_rate = self.coordinator.get_next_rate()
        if next_rate:
            attrs["next_rate"] = round(next_rate["value_inc_vat"], 2)
            attrs["next_rate_time"] = next_rate["valid_from"].isoformat()

        # Add daily stats
        stats = self.coordinator.get_daily_stats()
        if stats:
            attrs["today_min"] = round(stats["min"], 2)
            attrs["today_max"] = round(stats["max"], 2)
            attrs["today_average"] = round(stats["average"], 2)

        # Rate status
        if current:
            rate = current["value_inc_vat"]
            if rate < 0:
                attrs["rate_status"] = "negative"
            elif rate < 10:
                attrs["rate_status"] = "very_cheap"
            elif rate < 20:
                attrs["rate_status"] = "cheap"
            elif rate < 30:
                attrs["rate_status"] = "normal"
            elif rate < 40:
                attrs["rate_status"] = "expensive"
            else:
                attrs["rate_status"] = "very_expensive"

        return attrs


class NextRateSensor(OctopusAgileBaseSensor):
    """Sensor showing the next electricity rate."""

    _attr_icon = "mdi:clock-fast"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_next_rate"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Next rate"

    @property
    def native_value(self):
        """Return the next rate."""
        next_rate = self.coordinator.get_next_rate()
        return round(next_rate["value_inc_vat"], 2) if next_rate else None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        next_rate = self.coordinator.get_next_rate()
        if not next_rate:
            return {}
        
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        return {
            "valid_from": next_rate["valid_from"].isoformat(),
            "valid_to": next_rate["valid_to"].isoformat(),
            "minutes_until": max(
                0,
                int((next_rate["valid_from"] - now_utc).total_seconds() / 60),
            ),
        }


class TodayAverageRateSensor(OctopusAgileBaseSensor):
    """Sensor showing today's average rate."""

    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_today_average"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Today average rate"

    @property
    def native_value(self):
        """Return today's average rate."""
        stats = self.coordinator.get_daily_stats()
        return round(stats["average"], 2) if stats else None


class TodayMinRateSensor(OctopusAgileBaseSensor):
    """Sensor showing today's minimum rate."""

    _attr_icon = "mdi:arrow-down-bold"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_today_min"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Today minimum rate"

    @property
    def native_value(self):
        """Return today's minimum rate."""
        stats = self.coordinator.get_daily_stats()
        return round(stats["min"], 2) if stats else None


class TodayMaxRateSensor(OctopusAgileBaseSensor):
    """Sensor showing today's maximum rate."""

    _attr_icon = "mdi:arrow-up-bold"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_today_max"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Today maximum rate"

    @property
    def native_value(self):
        """Return today's maximum rate."""
        stats = self.coordinator.get_daily_stats()
        return round(stats["max"], 2) if stats else None


class TomorrowAverageRateSensor(OctopusAgileBaseSensor):
    """Sensor showing tomorrow's average rate."""

    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_tomorrow_average"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Tomorrow average rate"

    @property
    def native_value(self):
        """Return tomorrow's average rate."""
        tomorrow = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        stats = self.coordinator.get_daily_stats(tomorrow)
        return round(stats["average"], 2) if stats else None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        tomorrow = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        stats = self.coordinator.get_daily_stats(tomorrow)
        if not stats:
            return {"data_available": False}
        return {
            "data_available": True,
            "min": round(stats["min"], 2),
            "max": round(stats["max"], 2),
            "slot_count": stats["slot_count"],
        }


class TodayCheapestWindowSensor(OctopusAgileBaseSensor):
    """Sensor showing today's cheapest window start time."""

    _attr_icon = "mdi:clock-check"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry, consecutive_period: int, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self.consecutive_period = consecutive_period
        self._attr_unique_id = f"{entry.entry_id}_today_{consecutive_period}_cheapest_window"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"Today cheapest {self.consecutive_period}min window"

    @property
    def native_value(self):
        """Return the cheapest window start time."""
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        return start if start else None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        cost = self.coordinator.find_cheapest_window_cost(today_local, self.consecutive_period)
        
        attrs = {"period_minutes": self.consecutive_period}
        if start:
            end = start + timedelta(minutes=self.consecutive_period)
            now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
            attrs["end_time"] = end.isoformat()
            attrs["is_active"] = start <= now_utc < end
            attrs["minutes_until"] = max(0, int((start - now_utc).total_seconds() / 60)) if start > now_utc else 0
        if cost is not None:
            attrs["average_rate"] = round(cost, 2)
        return attrs


class TomorrowCheapestWindowSensor(OctopusAgileBaseSensor):
    """Sensor showing tomorrow's cheapest window start time."""

    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry, consecutive_period: int, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self.consecutive_period = consecutive_period
        self._attr_unique_id = f"{entry.entry_id}_tomorrow_{consecutive_period}_cheapest_window"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"Tomorrow cheapest {self.consecutive_period}min window"

    @property
    def native_value(self):
        """Return the cheapest window start time."""
        tomorrow_local = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        start = self.coordinator.find_cheapest_window(tomorrow_local, self.consecutive_period)
        return start if start else None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        tomorrow_local = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        start = self.coordinator.find_cheapest_window(tomorrow_local, self.consecutive_period)
        cost = self.coordinator.find_cheapest_window_cost(tomorrow_local, self.consecutive_period)
        
        attrs = {
            "period_minutes": self.consecutive_period,
            "data_available": start is not None,
        }
        if start:
            attrs["end_time"] = (start + timedelta(minutes=self.consecutive_period)).isoformat()
        if cost is not None:
            attrs["average_rate"] = round(cost, 2)
        return attrs


class TodayCheapestWindowCostSensor(OctopusAgileBaseSensor):
    """Sensor showing the average cost of today's cheapest window."""

    _attr_icon = "mdi:cash-check"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, consecutive_period: int, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self.consecutive_period = consecutive_period
        self._attr_unique_id = f"{entry.entry_id}_today_{consecutive_period}_cheapest_cost"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"Today cheapest {self.consecutive_period}min cost"

    @property
    def native_value(self):
        """Return the average cost of the cheapest window."""
        today_local = datetime.now(LONDON_TZ).date()
        cost = self.coordinator.find_cheapest_window_cost(today_local, self.consecutive_period)
        return round(cost, 2) if cost is not None else None
