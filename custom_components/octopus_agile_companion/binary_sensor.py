from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["octopus_agile_companion"][entry.entry_id]["coordinator"]
    async_add_entities([
        NegativePricingTodayBinarySensor(coordinator, entry),
        NegativePricingTomorrowBinarySensor(coordinator, entry)
    ], True)

class NegativePricingTodayBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "Today Negative Price"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_negative_price_today"

    @property
    def is_on(self):
        today_local = datetime.now(LONDON_TZ).date()
        return self._check_negative_prices(today_local)

    def _check_negative_prices(self, day):
        if day not in self.coordinator.rates_by_date:
            return False
        for slot in self.coordinator.rates_by_date[day]:
            if slot["value_inc_vat"] < 0:
                return True
        return False

class NegativePricingTomorrowBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "Tomorrow Negative Price"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_negative_price_tomorrow"

    @property
    def is_on(self):
        tomorrow_local = (datetime.now(LONDON_TZ).date() + timedelta(days=1))
        return self._check_negative_prices(tomorrow_local)

    def _check_negative_prices(self, day):
        if day not in self.coordinator.rates_by_date:
            return False
        for slot in self.coordinator.rates_by_date[day]:
            if slot["value_inc_vat"] < 0:
                return True
        return False
