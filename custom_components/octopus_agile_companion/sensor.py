from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from .const import DOMAIN, DATA_COORDINATOR, CONF_CONSECUTIVE_PERIODS

LONDON_TZ = ZoneInfo("Europe/London")

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[DATA_COORDINATOR]
    periods = data[CONF_CONSECUTIVE_PERIODS]

    entities = []
    for p in periods:
        entities.append(TodayCheapestWindowSensor(coordinator, entry, p))
        entities.append(TomorrowCheapestWindowSensor(coordinator, entry, p))
    async_add_entities(entities, True)

class TodayCheapestWindowSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator, entry, consecutive_period):
        super().__init__(coordinator)
        self.consecutive_period = consecutive_period
        self._attr_name = f"Today Cheapest {self.consecutive_period} mins Window Start"
        self._attr_unique_id = f"{entry.entry_id}_today_{self.consecutive_period}_cheapest_window"

    @property
    def native_value(self):
        today_local = datetime.now(LONDON_TZ).date()
        start = self.coordinator.find_cheapest_window(today_local, self.consecutive_period)
        return start.isoformat() if start else None


class TomorrowCheapestWindowSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator, entry, consecutive_period):
        super().__init__(coordinator)
        self.consecutive_period = consecutive_period
        self._attr_name = f"Tomorrow Cheapest {self.consecutive_period} mins Window Start"
        self._attr_unique_id = f"{entry.entry_id}_tomorrow_{self.consecutive_period}_cheapest_window"

    @property
    def native_value(self):
        tomorrow_local = (datetime.now(LONDON_TZ).date() + timedelta(days=1))
        start = self.coordinator.find_cheapest_window(tomorrow_local, self.consecutive_period)
        return start.isoformat() if start else None
