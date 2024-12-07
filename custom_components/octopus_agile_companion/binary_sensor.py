from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .const import DOMAIN, DATA_COORDINATOR, CONF_CONSECUTIVE_PERIODS

LONDON_TZ = ZoneInfo("Europe/London")

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    periods = hass.data[DOMAIN][entry.entry_id][CONF_CONSECUTIVE_PERIODS]

    entities = [
        NegativePricingTodayBinarySensor(coordinator, entry),
        NegativePricingTomorrowBinarySensor(coordinator, entry)
    ]

    # Add the cheapest window active binary sensors for each period (today only)
    for p in periods:
        entities.append(TodayCheapestWindowActiveBinarySensor(coordinator, entry, p))

    async_add_entities(entities, True)

class NegativePricingTodayBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "Today Negative Price"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_negative_price_today"

    @property
    def is_on(self):
        today_local = datetime.now(LONDON_TZ).date()
        if today_local not in self.coordinator.rates_by_date:
            return False
        return any(slot["value_inc_vat"] < 0 for slot in self.coordinator.rates_by_date[today_local])

class NegativePricingTomorrowBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "Tomorrow Negative Price"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_negative_price_tomorrow"

    @property
    def is_on(self):
        tomorrow_local = (datetime.now(LONDON_TZ).date() + timedelta(days=1))
        if tomorrow_local not in self.coordinator.rates_by_date:
            return False
        return any(slot["value_inc_vat"] < 0 for slot in self.coordinator.rates_by_date[tomorrow_local])

class TodayCheapestWindowActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is on during today's cheapest window."""

    def __init__(self, coordinator, entry, consecutive_period):
        super().__init__(coordinator)
        self.consecutive_period = consecutive_period
        self._attr_name = f"Today {self.consecutive_period} mins Window Active"
        self._attr_unique_id = f"{entry.entry_id}_today_{self.consecutive_period}_window_active"

    @property
    def is_on(self):
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        if not start:
            return False

        end = start + timedelta(minutes=self.consecutive_period)
        now_utc = datetime.utcnow().replace(tzinfo=None)
        return start <= now_utc < end
