"""DataUpdateCoordinator for Octopus Agile Companion."""
from __future__ import annotations

from datetime import datetime, timedelta, time
import logging
import async_timeout
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant
from zoneinfo import ZoneInfo

from .const import EXPECTED_SLOTS_PER_DAY, EVENT_RATES_UPDATED

_LOGGER = logging.getLogger(__name__)
LONDON_TZ = ZoneInfo("Europe/London")


class OctopusAgileCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches and stores Octopus Agile rates by local date."""

    def __init__(
        self,
        hass: HomeAssistant,
        api,
        fetch_window_start: str,
        fetch_window_end: str,
        entry_id: str,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="octopus_agile_companion_coordinator",
            update_interval=timedelta(minutes=30),
        )
        self.api = api
        self.fetch_window_start = self._parse_time(fetch_window_start)
        self.fetch_window_end = self._parse_time(fetch_window_end)
        self.entry_id = entry_id
        self.rates_by_date: dict[datetime.date, list[dict]] = {}
        self._last_rates_hash = None

    def _parse_time(self, t_str: str) -> time:
        """Parse time string to time object."""
        hr, mn = t_str.split(":")
        return time(int(hr), int(mn))

    def _get_local_date_for_slot(self, dt_utc: datetime) -> datetime.date:
        """Get local date for a UTC datetime."""
        dt_local = dt_utc.astimezone(LONDON_TZ)
        return dt_local.date()

    def _parse_iso_datetime(self, dt_str: str) -> datetime:
        """Parse ISO datetime string to datetime object."""
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    async def _async_update_data(self):
        """Fetch data from API."""
        now_local = datetime.now(LONDON_TZ).time()
        
        # Fetch if no data or within the fetch window
        if not self.rates_by_date or (self.fetch_window_start <= now_local <= self.fetch_window_end):
            try:
                async with async_timeout.timeout(30):
                    session = async_get_clientsession(self.hass)
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

                    for d in new_rates_by_date:
                        new_rates_by_date[d].sort(key=lambda x: x["valid_from"])
                        slot_count = len(new_rates_by_date[d])
                        if slot_count < EXPECTED_SLOTS_PER_DAY:
                            _LOGGER.warning(
                                "Data for %s is incomplete (%d slots). Will rely on future updates within fetch window.",
                                d, slot_count
                            )

                    if new_rates_by_date:
                        # Check if rates actually changed
                        new_hash = self._compute_rates_hash(new_rates_by_date)
                        if new_hash != self._last_rates_hash:
                            self._last_rates_hash = new_hash
                            self.rates_by_date = new_rates_by_date
                            # Fire event when rates update
                            self.hass.bus.async_fire(
                                EVENT_RATES_UPDATED,
                                {
                                    "entry_id": self.entry_id,
                                    "dates": [str(d) for d in new_rates_by_date.keys()],
                                },
                            )
                        _LOGGER.debug("Fetched rates for dates: %s", list(self.rates_by_date.keys()))
                    else:
                        _LOGGER.warning("No rates fetched at all. Keeping old data if any.")
                    return self.rates_by_date
            except Exception as err:
                _LOGGER.error("Error updating data: %s", err)
                raise UpdateFailed(f"Error updating data: {err}")
        else:
            return self.rates_by_date

    def _compute_rates_hash(self, rates_by_date: dict) -> str:
        """Compute a hash of the rates data for change detection."""
        items = []
        for date in sorted(rates_by_date.keys()):
            for slot in rates_by_date[date]:
                items.append(f"{slot['valid_from']}:{slot['value_inc_vat']}")
        return hash(tuple(items))

    def find_cheapest_window(self, day: datetime.date, period_minutes: int):
        """Find the start time of the cheapest consecutive window."""
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

    def find_cheapest_window_cost(self, day: datetime.date, period_minutes: int) -> float | None:
        """Find the average cost of the cheapest consecutive window."""
        if day not in self.rates_by_date:
            return None

        slots = self.rates_by_date[day]
        if not slots:
            return None

        slot_length = slots[0]["valid_to"] - slots[0]["valid_from"]
        period_td = timedelta(minutes=period_minutes)

        if period_td % slot_length != timedelta(0):
            return None

        required_slots = int(period_td / slot_length)
        best_cost = None

        for i in range(len(slots) - required_slots + 1):
            window_slots = slots[i:i+required_slots]
            window_cost = sum(s["value_inc_vat"] for s in window_slots) / required_slots
            if best_cost is None or window_cost < best_cost:
                best_cost = window_cost

        return best_cost

    def get_current_rate(self, day: datetime.date = None) -> dict | None:
        """Get the current rate slot."""
        if day is None:
            day = datetime.now(LONDON_TZ).date()
        if day not in self.rates_by_date:
            return None
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        for slot in self.rates_by_date[day]:
            if slot["valid_from"] <= now_utc < slot["valid_to"]:
                return slot
        return None

    def get_next_rate(self) -> dict | None:
        """Get the next rate slot."""
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        for day in [today, tomorrow]:
            if day not in self.rates_by_date:
                continue
            for slot in self.rates_by_date[day]:
                if slot["valid_from"] > now_utc:
                    return slot
        return None

    def get_daily_stats(self, day: datetime.date = None) -> dict | None:
        """Get daily statistics for rates."""
        if day is None:
            day = datetime.now(LONDON_TZ).date()
        if day not in self.rates_by_date:
            return None
        
        slots = self.rates_by_date[day]
        if not slots:
            return None
        
        values = [s["value_inc_vat"] for s in slots]
        return {
            "min": min(values),
            "max": max(values),
            "average": sum(values) / len(values),
            "slot_count": len(slots),
        }

    def get_rates_in_range(
        self, day: datetime.date, start_time: time = None, end_time: time = None
    ) -> list[dict]:
        """Get rates within a time range on a given day."""
        if day not in self.rates_by_date:
            return []
        
        slots = self.rates_by_date[day]
        if start_time is None and end_time is None:
            return slots
        
        result = []
        for slot in slots:
            slot_time = slot["valid_from"].astimezone(LONDON_TZ).time()
            if start_time and slot_time < start_time:
                continue
            if end_time and slot_time >= end_time:
                continue
            result.append(slot)
        return result

    def is_currently_cheap(self, threshold: float) -> bool:
        """Check if current rate is below threshold."""
        current = self.get_current_rate()
        if current is None:
            return False
        return current["value_inc_vat"] < threshold

    def is_currently_expensive(self, threshold: float) -> bool:
        """Check if current rate is above threshold."""
        current = self.get_current_rate()
        if current is None:
            return False
        return current["value_inc_vat"] > threshold

    def is_currently_negative(self) -> bool:
        """Check if current rate is negative (you get paid!)."""
        current = self.get_current_rate()
        if current is None:
            return False
        return current["value_inc_vat"] < 0

    def time_until_cheap(self, threshold: float) -> timedelta | None:
        """Get time until rate drops below threshold."""
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        for day in [today, tomorrow]:
            if day not in self.rates_by_date:
                continue
            for slot in self.rates_by_date[day]:
                if slot["valid_from"] > now_utc and slot["value_inc_vat"] < threshold:
                    return slot["valid_from"] - now_utc
        return None

    def time_until_expensive(self, threshold: float) -> timedelta | None:
        """Get time until rate rises above threshold."""
        now_utc = datetime.now(LONDON_TZ).astimezone(ZoneInfo("UTC"))
        today = datetime.now(LONDON_TZ).date()
        tomorrow = today + timedelta(days=1)
        
        for day in [today, tomorrow]:
            if day not in self.rates_by_date:
                continue
            for slot in self.rates_by_date[day]:
                if slot["valid_from"] > now_utc and slot["value_inc_vat"] > threshold:
                    return slot["valid_from"] - now_utc
        return None
