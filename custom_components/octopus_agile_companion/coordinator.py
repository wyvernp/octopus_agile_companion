from datetime import datetime, timedelta, time
import logging
import async_timeout
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from zoneinfo import ZoneInfo
from .const import EXPECTED_SLOTS_PER_DAY

_LOGGER = logging.getLogger(__name__)
LONDON_TZ = ZoneInfo("Europe/London")

class OctopusAgileCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api, fetch_window_start, fetch_window_end):
        super().__init__(
            hass,
            _LOGGER,
            name="octopus_agile_companion_coordinator",
            update_interval=timedelta(hours=1),
        )
        self.api = api
        self.fetch_window_start = self._parse_time(fetch_window_start)
        self.fetch_window_end = self._parse_time(fetch_window_end)
        self.rates_by_date = {}

    def _parse_time(self, t_str):
        hr, mn = t_str.split(":")
        return time(int(hr), int(mn))

    def _get_local_date_for_slot(self, dt_utc):
        dt_local = dt_utc.astimezone(LONDON_TZ)
        return dt_local.date()

    def _parse_iso_datetime(self, dt_str):
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    async def _async_update_data(self):
        now_local = datetime.now(LONDON_TZ).time()
        # If we have no data or are within the fetch window, fetch data
        if not self.rates_by_date or (self.fetch_window_start <= now_local <= self.fetch_window_end):
            try:
                async with async_timeout.timeout(30):
                    session = self.hass.helpers.aiohttp_client.async_get_clientsession()
                    results = await self.api.fetch_rates(session)

                    new_rates_by_date = {}
                    for r in results:
                        valid_from_utc = self._parse_iso_datetime(r["valid_from"])
                        valid_to_utc = self._parse_iso_datetime(r["valid_to"])
                        slot_date = self._get_local_date_for_slot(valid_from_utc)

                        if slot_date not in new_rates_by_date:
                            new_rates_by_date[slot_date] = []
                        new_rates_by_date[slot_date].append({
                            "valid_from": valid_from_utc,
                            "valid_to": valid_to_utc,
                            "value_inc_vat": r["value_inc_vat"]
                        })

                    # Sort and check completeness
                    for d in new_rates_by_date:
                        new_rates_by_date[d].sort(key=lambda x: x["valid_from"])
                        slot_count = len(new_rates_by_date[d])
                        if slot_count < EXPECTED_SLOTS_PER_DAY:
                            _LOGGER.warning(
                                "Data for %s is incomplete (%d slots). Will try again if within fetch window.",
                                d, slot_count
                            )

                    # Merge new data with existing data
                    self.rates_by_date = new_rates_by_date if new_rates_by_date else self.rates_by_date
                    if not self.rates_by_date:
                        _LOGGER.warning("No rates fetched at all.")
                    else:
                        _LOGGER.debug("Fetched rates for dates: %s", list(self.rates_by_date.keys()))

                    return self.rates_by_date
            except Exception as err:
                _LOGGER.error("Error updating data: %s", err)
                raise UpdateFailed(f"Error updating data: {err}")
        else:
            return self.rates_by_date

    def find_cheapest_window(self, day, period_minutes: int):
        if day not in self.rates_by_date:
            return None

        slots = self.rates_by_date[day]
        if not slots:
            return None

        slot_length = slots[0]["valid_to"] - slots[0]["valid_from"]
        period_td = timedelta(minutes=period_minutes)

        if period_td % slot_length != timedelta(0):
            _LOGGER.warning(
                "Requested consecutive period (%d min) doesn't align with slot boundaries (%s).",
                period_minutes, slot_length
            )
            return None

        required_slots = int(period_td / slot_length)
        best_start = None
        best_cost = None

        for i in range(len(slots) - required_slots + 1):
            window_slots = slots[i:i+required_slots]
            window_cost = sum(s["value_inc_vat"] for s in window_slots)
            if best_cost is None or window_cost < best_cost:
                best_cost = window_cost
                best_start = window_slots[0]["valid_from"]

        return best_start

    def get_current_rate(self, day):
        if day not in self.rates_by_date:
            return None
        now_utc = datetime.utcnow().replace(tzinfo=None)
        for slot in self.rates_by_date[day]:
            if slot["valid_from"] <= now_utc < slot["valid_to"]:
                return slot
        return None
