"""Sensor platform for Octopus Agile Companion."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    CONF_CONSECUTIVE_PERIODS,
    CONF_CHEAP_THRESHOLD,
    CONF_EXPENSIVE_THRESHOLD,
    CONF_FLAT_RATE_COMPARISON,
    CONF_USAGE_PROFILE,
    CONF_DAILY_KWH,
    CONF_EXPORT_RATE,
    CONF_BATTERY_CAPACITY,
    CONF_ENABLE_CARBON,
    DEFAULT_FLAT_RATE,
    DEFAULT_USAGE_PROFILE,
    DEFAULT_DAILY_KWH,
    DEFAULT_EXPORT_RATE,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_ENABLE_CARBON,
    ATTRIBUTION,
)
from .analytics import (
    SavingsCalculator,
    ExportOptimizer,
    UsagePatternAnalyzer,
    CarbonIntensityAPI,
)

_LOGGER = logging.getLogger(__name__)
LONDON_TZ = ZoneInfo("Europe/London")

# Update interval for carbon intensity sensors (30 min to match data updates)
SCAN_INTERVAL = timedelta(minutes=30)


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

    # Analytics sensors
    flat_rate = data.get(CONF_FLAT_RATE_COMPARISON, DEFAULT_FLAT_RATE)
    usage_profile = data.get(CONF_USAGE_PROFILE, DEFAULT_USAGE_PROFILE)
    daily_kwh = data.get(CONF_DAILY_KWH, DEFAULT_DAILY_KWH)
    export_rate = data.get(CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE)
    battery_capacity = data.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
    enable_carbon = data.get(CONF_ENABLE_CARBON, DEFAULT_ENABLE_CARBON)
    
    # Add savings calculator sensors
    entities.extend([
        EstimatedDailyCostSensor(coordinator, entry, device_info, flat_rate, usage_profile, daily_kwh),
        PotentialDailySavingsSensor(coordinator, entry, device_info, flat_rate, usage_profile, daily_kwh),
        EffectiveRateSensor(coordinator, entry, device_info, usage_profile, daily_kwh),
        UsageOptimizationScoreSensor(coordinator, entry, device_info, usage_profile, daily_kwh),
        BestTimeForLoadSensor(coordinator, entry, device_info),
    ])
    
    # Add battery/export sensors if battery capacity is configured
    if battery_capacity > 0:
        entities.extend([
            BestChargeWindowSensor(coordinator, entry, device_info, battery_capacity),
            ExportArbitrageSensor(coordinator, entry, device_info, export_rate, battery_capacity),
        ])
    
    # Add carbon intensity sensors if enabled
    if enable_carbon:
        entities.extend([
            CarbonIntensitySensor(hass, entry, device_info),
            GreenestWindowSensor(hass, coordinator, entry, device_info),
        ])

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
        """Return the cheapest window as a formatted time range."""
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        if not start:
            return None
        start_local = start.astimezone(LONDON_TZ)
        end_local = start_local + timedelta(minutes=self.consecutive_period)
        return f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}"

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        cost = self.coordinator.find_cheapest_window_cost(today_local, self.consecutive_period)
        
        attrs = {"period_minutes": self.consecutive_period}
        if start:
            start_local = start.astimezone(LONDON_TZ)
            end = start + timedelta(minutes=self.consecutive_period)
            end_local = end.astimezone(LONDON_TZ)
            now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
            attrs["start_time"] = start_local.strftime("%H:%M")
            attrs["end_time"] = end_local.strftime("%H:%M")
            attrs["start_iso"] = start.isoformat()
            attrs["end_iso"] = end.isoformat()
            attrs["is_active"] = start <= now_utc < end
            attrs["minutes_until"] = max(0, int((start - now_utc).total_seconds() / 60)) if start > now_utc else 0
        if cost is not None:
            attrs["average_rate"] = round(cost, 2)
        return attrs


class TomorrowCheapestWindowSensor(OctopusAgileBaseSensor):
    """Sensor showing tomorrow's cheapest window start time."""

    _attr_icon = "mdi:clock-check-outline"

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
        """Return the cheapest window as a formatted time range."""
        tomorrow_local = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        start = self.coordinator.find_cheapest_window(tomorrow_local, self.consecutive_period)
        if not start:
            return None
        start_local = start.astimezone(LONDON_TZ)
        end_local = start_local + timedelta(minutes=self.consecutive_period)
        return f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}"

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
            start_local = start.astimezone(LONDON_TZ)
            end_local = (start + timedelta(minutes=self.consecutive_period)).astimezone(LONDON_TZ)
            attrs["start_time"] = start_local.strftime("%H:%M")
            attrs["end_time"] = end_local.strftime("%H:%M")
            attrs["start_iso"] = start.isoformat()
            attrs["end_iso"] = (start + timedelta(minutes=self.consecutive_period)).isoformat()
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


# =============================================================================
# Analytics Sensors
# =============================================================================


class EstimatedDailyCostSensor(OctopusAgileBaseSensor):
    """Sensor showing estimated daily cost based on usage profile."""

    _attr_icon = "mdi:currency-gbp"
    _attr_native_unit_of_measurement = "p"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator, entry, device_info: DeviceInfo,
        flat_rate: float, usage_profile: str, daily_kwh: float
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_estimated_daily_cost"
        self.flat_rate = flat_rate
        self.usage_profile = usage_profile
        self.daily_kwh = daily_kwh
        self._calculator = SavingsCalculator(flat_rate)
        self._analyzer = UsagePatternAnalyzer(usage_profile)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Estimated daily cost"

    @property
    def native_value(self):
        """Return the estimated daily cost."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return None
        
        rates = self.coordinator.rates_by_date[today]
        result = self._calculator.estimate_daily_cost(
            rates,
            self._analyzer.get_profile(),
            self.daily_kwh
        )
        return round(result["estimated_cost_pence"], 0)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return {"data_available": False}
        
        rates = self.coordinator.rates_by_date[today]
        result = self._calculator.estimate_daily_cost(
            rates,
            self._analyzer.get_profile(),
            self.daily_kwh
        )
        return {
            "data_available": True,
            "estimated_cost_pounds": result["estimated_cost_pounds"],
            "flat_rate_cost_pence": result["flat_rate_cost_pence"],
            "flat_rate_cost_pounds": result["flat_rate_cost_pounds"],
            "daily_kwh": self.daily_kwh,
            "usage_profile": self.usage_profile,
            "flat_rate_comparison": self.flat_rate,
        }


class PotentialDailySavingsSensor(OctopusAgileBaseSensor):
    """Sensor showing potential daily savings vs flat rate."""

    _attr_icon = "mdi:piggy-bank"
    _attr_native_unit_of_measurement = "p"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator, entry, device_info: DeviceInfo,
        flat_rate: float, usage_profile: str, daily_kwh: float
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_potential_daily_savings"
        self.flat_rate = flat_rate
        self.usage_profile = usage_profile
        self.daily_kwh = daily_kwh
        self._calculator = SavingsCalculator(flat_rate)
        self._analyzer = UsagePatternAnalyzer(usage_profile)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Potential daily savings"

    @property
    def native_value(self):
        """Return potential daily savings."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return None
        
        rates = self.coordinator.rates_by_date[today]
        result = self._calculator.estimate_daily_cost(
            rates,
            self._analyzer.get_profile(),
            self.daily_kwh
        )
        return round(result["potential_savings_pence"], 0)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return {"data_available": False}
        
        rates = self.coordinator.rates_by_date[today]
        result = self._calculator.estimate_daily_cost(
            rates,
            self._analyzer.get_profile(),
            self.daily_kwh
        )
        
        # Calculate monthly/yearly projections
        daily_savings = result["potential_savings_pence"]
        return {
            "data_available": True,
            "savings_pounds": result["potential_savings_pounds"],
            "monthly_projection_pounds": round(daily_savings * 30 / 100, 2),
            "yearly_projection_pounds": round(daily_savings * 365 / 100, 2),
            "vs_flat_rate": self.flat_rate,
        }


class EffectiveRateSensor(OctopusAgileBaseSensor):
    """Sensor showing the effective rate based on usage profile."""

    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator, entry, device_info: DeviceInfo,
        usage_profile: str, daily_kwh: float
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_effective_rate"
        self.usage_profile = usage_profile
        self.daily_kwh = daily_kwh
        self._analyzer = UsagePatternAnalyzer(usage_profile)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Effective rate"

    @property
    def native_value(self):
        """Return the effective rate."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return None
        
        rates = self.coordinator.rates_by_date[today]
        profile = self._analyzer.get_profile()
        total_weight = sum(profile.values())
        
        # Calculate weighted average rate
        weighted_rate = 0.0
        for slot in rates:
            hour = slot["valid_from"].astimezone(LONDON_TZ).hour
            weight = profile.get(hour, 1.0) / total_weight
            # Calculate actual slot duration
            slot_duration_hours = (slot["valid_to"] - slot["valid_from"]).total_seconds() / 3600
            slots_per_hour = 1.0 / slot_duration_hours if slot_duration_hours > 0 else 2
            weighted_rate += slot["value_inc_vat"] * weight / slots_per_hour
        
        return round(weighted_rate, 2)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        stats = self.coordinator.get_daily_stats(today)
        if not stats:
            return {}
        
        return {
            "simple_average": round(stats["average"], 2),
            "usage_profile": self.usage_profile,
            "comparison": "effective vs simple average considers your usage pattern",
        }


class UsageOptimizationScoreSensor(OctopusAgileBaseSensor):
    """Sensor showing how well usage aligns with cheap rates."""

    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator, entry, device_info: DeviceInfo,
        usage_profile: str, daily_kwh: float
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_optimization_score"
        self.usage_profile = usage_profile
        self.daily_kwh = daily_kwh
        self._analyzer = UsagePatternAnalyzer(usage_profile)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Usage optimization score"

    @property
    def native_value(self):
        """Return the optimization score."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return None
        
        rates = self.coordinator.rates_by_date[today]
        result = self._analyzer.analyze_rates_by_profile(rates, self.daily_kwh)
        return round(result["optimization_score"], 0)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return {"data_available": False}
        
        rates = self.coordinator.rates_by_date[today]
        result = self._analyzer.analyze_rates_by_profile(rates, self.daily_kwh)
        
        return {
            "data_available": True,
            "usage_profile": self.usage_profile,
            "cheapest_hours": result["cheapest_hours"],
            "expensive_hours": result["expensive_hours"],
            "usage_in_cheap_hours": f"{result['usage_in_cheap_hours_percent']}%",
            "usage_in_expensive_hours": f"{result['usage_in_expensive_hours_percent']}%",
            "recommendations": result["recommendations"],
        }


class BestTimeForLoadSensor(OctopusAgileBaseSensor):
    """Sensor recommending best time to run appliances."""

    _attr_icon = "mdi:washing-machine"

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_best_load_time"
        self._analyzer = UsagePatternAnalyzer()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Best time for appliances"

    @property
    def native_value(self):
        """Return best time for a typical 2-hour appliance load as formatted time range."""
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        # Combine today remaining and tomorrow rates
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        rates = []
        
        for day in [today, tomorrow]:
            if day in self.coordinator.rates_by_date:
                for slot in self.coordinator.rates_by_date[day]:
                    if slot["valid_from"] >= now_utc:
                        rates.append(slot)
        
        if not rates:
            return None
        
        # Find best 2-hour window (typical appliance cycle)
        result = self._analyzer.suggest_load_shift(rates, load_kwh=1.5, duration_hours=2.0)
        if "error" in result:
            return None
        
        start = datetime.fromisoformat(result["recommended_start"]).astimezone(LONDON_TZ)
        end = datetime.fromisoformat(result["recommended_end"]).astimezone(LONDON_TZ)
        return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        rates = []
        
        for day in [today, tomorrow]:
            if day in self.coordinator.rates_by_date:
                for slot in self.coordinator.rates_by_date[day]:
                    if slot["valid_from"] >= now_utc:
                        rates.append(slot)
        
        if not rates:
            return {"data_available": False}
        
        result = self._analyzer.suggest_load_shift(rates, load_kwh=1.5, duration_hours=2.0)
        if "error" in result:
            return {"error": result["error"]}
        
        start = datetime.fromisoformat(result["recommended_start"]).astimezone(LONDON_TZ)
        end = datetime.fromisoformat(result["recommended_end"]).astimezone(LONDON_TZ)
        
        return {
            "data_available": True,
            "start_time": start.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M"),
            "start_iso": result["recommended_start"],
            "end_iso": result["recommended_end"],
            "optimal_rate": result["optimal_rate"],
            "savings_vs_now_pence": result["savings_vs_now_pence"],
            "savings_vs_average_pence": result["savings_vs_average_pence"],
            "appliance_examples": "washing machine, dishwasher, tumble dryer",
            "assumed_kwh": 1.5,
            "assumed_duration": "2 hours",
        }


class BestChargeWindowSensor(OctopusAgileBaseSensor):
    """Sensor showing best window to charge battery/EV."""

    _attr_icon = "mdi:battery-charging"

    def __init__(
        self, coordinator, entry, device_info: DeviceInfo,
        battery_capacity: float
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_best_charge_window"
        self.battery_capacity = battery_capacity
        self._optimizer = ExportOptimizer(battery_capacity_kwh=battery_capacity)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Best battery charge window"

    @property
    def native_value(self):
        """Return best charge window as formatted time range."""
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        rates = []
        
        for day in [today, tomorrow]:
            if day in self.coordinator.rates_by_date:
                for slot in self.coordinator.rates_by_date[day]:
                    if slot["valid_from"] >= now_utc:
                        rates.append(slot)
        
        if len(rates) < 2:
            return None
        
        result = self._optimizer.find_best_charge_window(
            rates,
            required_kwh=self.battery_capacity,
            charge_rate_kw=3.0
        )
        start = datetime.fromisoformat(result["start_time"]).astimezone(LONDON_TZ)
        end = datetime.fromisoformat(result["end_time"]).astimezone(LONDON_TZ)
        return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        rates = []
        
        for day in [today, tomorrow]:
            if day in self.coordinator.rates_by_date:
                for slot in self.coordinator.rates_by_date[day]:
                    if slot["valid_from"] >= now_utc:
                        rates.append(slot)
        
        if len(rates) < 2:
            return {"data_available": False}
        
        result = self._optimizer.find_best_charge_window(
            rates,
            required_kwh=self.battery_capacity,
            charge_rate_kw=3.0
        )
        start = datetime.fromisoformat(result["start_time"]).astimezone(LONDON_TZ)
        end = datetime.fromisoformat(result["end_time"]).astimezone(LONDON_TZ)
        return {
            "data_available": True,
            "start_time": start.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M"),
            "start_iso": result["start_time"],
            "end_iso": result["end_time"],
            "duration_minutes": result["duration_minutes"],
            "total_kwh": result["total_kwh"],
            "average_rate": result["average_rate"],
            "total_cost_pence": result["total_cost_pence"],
            "battery_capacity_kwh": self.battery_capacity,
        }


class ExportArbitrageSensor(OctopusAgileBaseSensor):
    """Sensor showing potential battery arbitrage value."""

    _attr_icon = "mdi:cash-multiple"
    _attr_native_unit_of_measurement = "p"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator, entry, device_info: DeviceInfo,
        export_rate: float, battery_capacity: float
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_export_arbitrage"
        self.export_rate = export_rate
        self.battery_capacity = battery_capacity
        self._optimizer = ExportOptimizer(
            export_rate=export_rate,
            battery_capacity_kwh=battery_capacity
        )

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Battery arbitrage potential"

    @property
    def native_value(self):
        """Return potential arbitrage value."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return None
        
        rates = self.coordinator.rates_by_date[today]
        result = self._optimizer.analyze_export_windows(rates)
        return round(result["potential_arbitrage_pence"], 0)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return {"data_available": False}
        
        rates = self.coordinator.rates_by_date[today]
        result = self._optimizer.analyze_export_windows(rates)
        
        # Count recommendation types
        actions = {}
        for rec in result["recommendations"]:
            action = rec["action"]
            actions[action] = actions.get(action, 0) + 1
        
        return {
            "data_available": True,
            "export_rate": self.export_rate,
            "battery_capacity_kwh": self.battery_capacity,
            "store_window_count": result["store_window_count"],
            "export_window_count": result["export_window_count"],
            "action_summary": actions,
            "monthly_potential_pounds": round(result["potential_arbitrage_pence"] * 30 / 100, 2),
        }


class CarbonIntensitySensor(SensorEntity):
    """Sensor showing current grid carbon intensity."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:molecule-co2"
    _attr_native_unit_of_measurement = "gCO2/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_attribution = "Data provided by National Grid ESO"
    _attr_should_poll = True  # Enable polling for non-coordinator sensor

    def __init__(self, hass, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_carbon_intensity"
        self._api = CarbonIntensityAPI()
        self._data = None

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Grid carbon intensity"

    @property
    def native_value(self):
        """Return the current carbon intensity."""
        return self._data.intensity if self._data else None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        if not self._data:
            return {"data_available": False}
        
        return {
            "data_available": True,
            "index": self._data.index,
            "valid_from": self._data.from_time.isoformat(),
            "valid_to": self._data.to_time.isoformat(),
            "description": self._get_description(self._data.index),
        }

    def _get_description(self, index: str) -> str:
        """Get human-readable description of carbon index."""
        descriptions = {
            "very low": "Excellent - mostly renewable generation",
            "low": "Good - high renewable mix",
            "moderate": "Average grid mix",
            "high": "Above average carbon emissions",
            "very high": "Poor - high fossil fuel generation",
        }
        return descriptions.get(index, "Unknown")

    async def async_update(self):
        """Update the sensor."""
        session = async_get_clientsession(self.hass)
        self._data = await self._api.fetch_current(session)


class GreenestWindowSensor(SensorEntity):
    """Sensor showing the greenest (lowest carbon) window."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:leaf"
    _attr_attribution = "Carbon data from National Grid ESO, prices from Octopus Energy"
    _attr_should_poll = True  # Enable polling for non-coordinator sensor

    def __init__(self, hass, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        self.hass = hass
        self.coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_greenest_window"
        self._api = CarbonIntensityAPI()
        self._forecast = []
        self._best_slot = None

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Greenest cheap window"

    @property
    def native_value(self):
        """Return the greenest cheap window as formatted time."""
        if not self._forecast:
            return None
        
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date:
            return None
        
        # Find overlap between cheap rates and low carbon
        rates = self.coordinator.rates_by_date[today]
        avg_rate = sum(s["value_inc_vat"] for s in rates) / len(rates)
        
        # Score each slot by combining price and carbon
        best_slot = None
        best_score = float("inf")
        
        for slot in rates:
            # Find matching carbon data
            slot_time = slot["valid_from"]
            carbon_data = next(
                (c for c in self._forecast 
                 if c.from_time <= slot_time < c.to_time),
                None
            )
            
            if carbon_data:
                # Normalize both to 0-1 scale and combine
                # Lower is better for both
                price_score = slot["value_inc_vat"] / avg_rate if avg_rate > 0 else 1
                carbon_score = carbon_data.intensity / 200  # Typical max ~400
                combined = price_score * 0.6 + carbon_score * 0.4  # Weight price more
                
                if combined < best_score:
                    best_score = combined
                    best_slot = slot
        
        self._best_slot = best_slot
        if not best_slot:
            return None
        
        start_local = best_slot["valid_from"].astimezone(LONDON_TZ)
        end_local = best_slot["valid_to"].astimezone(LONDON_TZ)
        return f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}"

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today = datetime.now(LONDON_TZ).date()
        if today not in self.coordinator.rates_by_date or not self._forecast:
            return {"data_available": False}
        
        rates = self.coordinator.rates_by_date[today]
        
        # Find cheapest 6 hours and check their carbon intensity
        sorted_rates = sorted(rates, key=lambda x: x["value_inc_vat"])[:12]  # 6 hours = 12 slots
        
        carbon_during_cheap = []
        for slot in sorted_rates:
            carbon_data = next(
                (c for c in self._forecast 
                 if c.from_time <= slot["valid_from"] < c.to_time),
                None
            )
            if carbon_data:
                carbon_during_cheap.append(carbon_data.intensity)
        
        avg_carbon_cheap = sum(carbon_during_cheap) / len(carbon_during_cheap) if carbon_during_cheap else None
        
        return {
            "data_available": True,
            "avg_carbon_during_cheap_periods": round(avg_carbon_cheap, 0) if avg_carbon_cheap else None,
            "carbon_data_points": len(self._forecast),
            "tip": "Running appliances during this window saves money AND carbon!",
        }

    async def async_update(self):
        """Update the sensor."""
        session = async_get_clientsession(self.hass)
        self._forecast = await self._api.fetch_forecast(session, hours=24)
