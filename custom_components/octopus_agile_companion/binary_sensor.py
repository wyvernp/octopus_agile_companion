"""Binary sensor platform for Octopus Agile Companion."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    CONF_CONSECUTIVE_PERIODS,
    CONF_CHEAP_THRESHOLD,
    CONF_EXPENSIVE_THRESHOLD,
    ATTRIBUTION,
    DEFAULT_CHEAP_THRESHOLD,
    DEFAULT_EXPENSIVE_THRESHOLD,
)

LONDON_TZ = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")


class _TimeBoundaryUpdateMixin:
    """Mixin that schedules a state write at the next known boundary."""

    _unsub_timer = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._schedule_next_update()

    async def async_will_remove_from_hass(self):
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        await super().async_will_remove_from_hass()

    def _schedule_at(self, when: datetime | None) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        if when is None:
            return

        when_utc = dt_util.as_utc(when)
        now_utc = dt_util.utcnow()
        if when_utc <= now_utc:
            when_utc = now_utc + timedelta(seconds=1)

        self._unsub_timer = async_track_point_in_time(
            self.hass,
            self._handle_boundary,
            when_utc,
        )

    async def _handle_boundary(self, _now) -> None:
        # Recompute state/attributes and schedule the next boundary.
        self.async_write_ha_state()
        self._schedule_next_update()

    def _schedule_next_update(self) -> None:
        raise NotImplementedError


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Octopus Agile binary sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[DATA_COORDINATOR]
    periods = data[CONF_CONSECUTIVE_PERIODS]
    device_info = data["device_info"]
    cheap_threshold = data.get(CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD)
    expensive_threshold = data.get(CONF_EXPENSIVE_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD)

    entities = [
        # Negative pricing indicators
        NegativePricingTodayBinarySensor(coordinator, entry, device_info),
        NegativePricingTomorrowBinarySensor(coordinator, entry, device_info),
        # Current negative rate
        CurrentlyNegativeBinarySensor(coordinator, entry, device_info),
        # Threshold-based sensors
        CurrentlyCheapBinarySensor(coordinator, entry, device_info, cheap_threshold),
        CurrentlyExpensiveBinarySensor(coordinator, entry, device_info, expensive_threshold),
    ]

    # Add the cheapest window active binary sensors for each period (today only)
    for p in periods:
        entities.append(TodayCheapestWindowActiveBinarySensor(coordinator, entry, p, device_info))

    async_add_entities(entities, True)


class OctopusAgileBinaryBaseSensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for Octopus Agile binary sensors."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = device_info


class OctopusAgileTimeSensitiveBinarySensor(_TimeBoundaryUpdateMixin, OctopusAgileBinaryBaseSensor):
    """Base class for time-sensitive binary sensors.

    These sensors don't need constant polling; they schedule their own
    updates at known time boundaries (typically the next rate slot boundary).
    """

    def _next_rate_boundary(self) -> datetime | None:
        current = self.coordinator.get_current_rate()
        if current:
            return current["valid_to"]

        next_rate = self.coordinator.get_next_rate()
        if next_rate:
            return next_rate["valid_from"]

        return None

    def _schedule_next_update(self) -> None:
        self._schedule_at(self._next_rate_boundary())

    def async_handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Reschedule our next boundary whenever fresh rate data arrives, since
        the next relevant boundary can change (e.g. once tomorrow's rates are
        available, or if the cheapest window shifts).
        """
        super().async_handle_coordinator_update()
        self._schedule_next_update()


class NegativePricingTodayBinarySensor(OctopusAgileBinaryBaseSensor):
    """Binary sensor indicating if today has any negative pricing."""

    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_negative_price_today"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Today has negative pricing"

    @property
    def is_on(self):
        """Return True if today has negative pricing."""
        today_local = datetime.now(LONDON_TZ).date()
        if today_local not in self.coordinator.rates_by_date:
            return False
        return any(
            slot["value_inc_vat"] < 0
            for slot in self.coordinator.rates_by_date[today_local]
        )

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        today_local = datetime.now(LONDON_TZ).date()
        if today_local not in self.coordinator.rates_by_date:
            return {"negative_slots": 0}
        
        negative_slots = [
            slot for slot in self.coordinator.rates_by_date[today_local]
            if slot["value_inc_vat"] < 0
        ]
        return {
            "negative_slots": len(negative_slots),
            "negative_periods": [
                {
                    "from": slot["valid_from"].isoformat(),
                    "to": slot["valid_to"].isoformat(),
                    "rate": round(slot["value_inc_vat"], 2),
                }
                for slot in negative_slots
            ],
        }


class NegativePricingTomorrowBinarySensor(OctopusAgileBinaryBaseSensor):
    """Binary sensor indicating if tomorrow has any negative pricing."""

    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_negative_price_tomorrow"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Tomorrow has negative pricing"

    @property
    def is_on(self):
        """Return True if tomorrow has negative pricing."""
        tomorrow_local = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        if tomorrow_local not in self.coordinator.rates_by_date:
            return False
        return any(
            slot["value_inc_vat"] < 0
            for slot in self.coordinator.rates_by_date[tomorrow_local]
        )

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        tomorrow_local = datetime.now(LONDON_TZ).date() + timedelta(days=1)
        if tomorrow_local not in self.coordinator.rates_by_date:
            return {"data_available": False, "negative_slots": 0}
        
        negative_slots = [
            slot for slot in self.coordinator.rates_by_date[tomorrow_local]
            if slot["value_inc_vat"] < 0
        ]
        return {
            "data_available": True,
            "negative_slots": len(negative_slots),
            "negative_periods": [
                {
                    "from": slot["valid_from"].isoformat(),
                    "to": slot["valid_to"].isoformat(),
                    "rate": round(slot["value_inc_vat"], 2),
                }
                for slot in negative_slots
            ],
        }


class CurrentlyNegativeBinarySensor(OctopusAgileTimeSensitiveBinarySensor):
    """Binary sensor indicating if current rate is negative (you get paid!)."""

    _attr_icon = "mdi:cash-fast"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator, entry, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_currently_negative"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Currently negative rate"

    @property
    def is_on(self):
        """Return True if current rate is negative."""
        return self.coordinator.is_currently_negative()

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        current = self.coordinator.get_current_rate()
        if not current:
            return {}
        return {
            "current_rate": round(current["value_inc_vat"], 2),
            "valid_until": current["valid_to"].astimezone(LONDON_TZ).strftime("%H:%M"),
            "valid_until_iso": current["valid_to"].isoformat(),
        }


class CurrentlyCheapBinarySensor(OctopusAgileTimeSensitiveBinarySensor):
    """Binary sensor indicating if current rate is below the cheap threshold."""

    _attr_icon = "mdi:tag-check"

    def __init__(self, coordinator, entry, device_info: DeviceInfo, threshold: float):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self.threshold = threshold
        self._attr_unique_id = f"{entry.entry_id}_currently_cheap"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Currently cheap rate"

    @property
    def is_on(self):
        """Return True if current rate is below threshold."""
        return self.coordinator.is_currently_cheap(self.threshold)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        current = self.coordinator.get_current_rate()
        time_until = self.coordinator.time_until_cheap(self.threshold)
        attrs = {"threshold": self.threshold}
        if current:
            attrs["current_rate"] = round(current["value_inc_vat"], 2)
        if time_until and not self.is_on:
            attrs["minutes_until_cheap"] = int(time_until.total_seconds() / 60)
        return attrs


class CurrentlyExpensiveBinarySensor(OctopusAgileTimeSensitiveBinarySensor):
    """Binary sensor indicating if current rate is above the expensive threshold."""

    _attr_icon = "mdi:tag-remove"

    def __init__(self, coordinator, entry, device_info: DeviceInfo, threshold: float):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self.threshold = threshold
        self._attr_unique_id = f"{entry.entry_id}_currently_expensive"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Currently expensive rate"

    @property
    def is_on(self):
        """Return True if current rate is above threshold."""
        return self.coordinator.is_currently_expensive(self.threshold)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        current = self.coordinator.get_current_rate()
        time_until = self.coordinator.time_until_expensive(self.threshold)
        attrs = {"threshold": self.threshold}
        if current:
            attrs["current_rate"] = round(current["value_inc_vat"], 2)
        if time_until and not self.is_on:
            attrs["minutes_until_expensive"] = int(time_until.total_seconds() / 60)
        return attrs


class TodayCheapestWindowActiveBinarySensor(OctopusAgileTimeSensitiveBinarySensor):
    """Binary sensor that is on during today's cheapest window."""

    _attr_icon = "mdi:clock-check"

    def __init__(self, coordinator, entry, consecutive_period: int, device_info: DeviceInfo):
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self.consecutive_period = consecutive_period
        self._attr_unique_id = f"{entry.entry_id}_today_{consecutive_period}_window_active"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"Cheapest {self.consecutive_period}min window active"

    @property
    def is_on(self):
        """Return True if currently within the cheapest window."""
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        if not start:
            return False

        end = start + timedelta(minutes=self.consecutive_period)
        now_utc = datetime.now(UTC)
        return start <= now_utc < end

    def _schedule_next_update(self) -> None:
        """Schedule updates at the next relevant boundary.

        We already know the window start/end; schedule exactly at those times.
        If the window isn't known yet, fall back to the next rate slot boundary.
        """
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        if not start:
            self._schedule_at(self._next_rate_boundary())
            return

        end = start + timedelta(minutes=self.consecutive_period)
        now_utc = datetime.now(UTC)

        if now_utc < start:
            self._schedule_at(start)
        elif now_utc < end:
            self._schedule_at(end)
        else:
            # Window is over for today; no further time-driven updates needed.
            self._schedule_at(None)

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
            now_utc = datetime.now(UTC)
            attrs["window_start"] = start_local.strftime("%H:%M")
            attrs["window_end"] = end_local.strftime("%H:%M")
            attrs["window_start_iso"] = start.isoformat()
            attrs["window_end_iso"] = end.isoformat()
            attrs["is_active"] = start <= now_utc < end
        if cost is not None:
            attrs["average_rate"] = round(cost, 2)
        return attrs
