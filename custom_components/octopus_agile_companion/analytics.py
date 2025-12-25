"""Advanced analytics module for Octopus Agile Companion."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from typing import Optional
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)
LONDON_TZ = ZoneInfo("Europe/London")


@dataclass
class UsageRecord:
    """A single usage record."""
    timestamp: datetime
    kwh: float
    rate: float
    cost: float  # in pence


@dataclass
class DailyAnalytics:
    """Daily analytics summary."""
    date: date
    total_kwh: float = 0.0
    total_cost: float = 0.0  # pence
    flat_rate_cost: float = 0.0  # pence
    savings: float = 0.0  # pence
    average_rate_paid: float = 0.0
    peak_usage_hour: Optional[int] = None
    cheapest_usage_hour: Optional[int] = None


@dataclass
class CarbonIntensityData:
    """Carbon intensity data for a time slot."""
    from_time: datetime
    to_time: datetime
    intensity: int  # gCO2/kWh
    index: str  # very low, low, moderate, high, very high


class CarbonIntensityAPI:
    """Wrapper for National Grid Carbon Intensity API."""
    
    BASE_URL = "https://api.carbonintensity.org.uk"
    
    async def fetch_current(self, session) -> Optional[CarbonIntensityData]:
        """Fetch current carbon intensity."""
        try:
            async with session.get(f"{self.BASE_URL}/intensity") as resp:
                resp.raise_for_status()
                data = await resp.json()
                intensity_data = data["data"][0]
                intensity_value = (
                    intensity_data["intensity"]["actual"] 
                    or intensity_data["intensity"]["forecast"] 
                    or 0
                )
                return CarbonIntensityData(
                    from_time=datetime.fromisoformat(intensity_data["from"].replace("Z", "+00:00")),
                    to_time=datetime.fromisoformat(intensity_data["to"].replace("Z", "+00:00")),
                    intensity=intensity_value,
                    index=intensity_data["intensity"]["index"] or "unknown",
                )
        except Exception as e:
            _LOGGER.error("Failed to fetch carbon intensity: %s", e)
            return None
    
    async def fetch_forecast(self, session, hours: int = 48) -> list[CarbonIntensityData]:
        """Fetch carbon intensity forecast."""
        try:
            # Use UTC for API calls to avoid BST/GMT confusion
            now_utc = datetime.now(ZoneInfo("UTC"))
            end_utc = now_utc + timedelta(hours=hours)
            url = f"{self.BASE_URL}/intensity/{now_utc.strftime('%Y-%m-%dT%H:%MZ')}/{end_utc.strftime('%Y-%m-%dT%H:%MZ')}"
            
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
                
                results = []
                for item in data.get("data", []):
                    intensity_value = (
                        item["intensity"]["actual"] 
                        or item["intensity"]["forecast"] 
                        or 0
                    )
                    results.append(CarbonIntensityData(
                        from_time=datetime.fromisoformat(item["from"].replace("Z", "+00:00")),
                        to_time=datetime.fromisoformat(item["to"].replace("Z", "+00:00")),
                        intensity=intensity_value,
                        index=item["intensity"]["index"] or "unknown",
                    ))
                return results
        except Exception as e:
            _LOGGER.error("Failed to fetch carbon forecast: %s", e)
            return []

    async def fetch_regional(
        self, session, postcode: str
    ) -> Optional[CarbonIntensityData]:
        """Fetch regional carbon intensity by postcode."""
        try:
            # Use first part of postcode (outward code)
            outward = postcode.split()[0] if " " in postcode else postcode[:4]
            async with session.get(f"{self.BASE_URL}/regional/postcode/{outward}") as resp:
                resp.raise_for_status()
                data = await resp.json()
                region_data = data["data"][0]["data"][0]
                intensity_value = region_data["intensity"]["forecast"] or 0
                return CarbonIntensityData(
                    from_time=datetime.fromisoformat(data["data"][0]["from"].replace("Z", "+00:00")),
                    to_time=datetime.fromisoformat(data["data"][0]["to"].replace("Z", "+00:00")),
                    intensity=intensity_value,
                    index=region_data["intensity"]["index"] or "unknown",
                )
        except Exception as e:
            _LOGGER.debug("Failed to fetch regional carbon intensity: %s", e)
            return None


class SavingsCalculator:
    """Calculate savings compared to flat-rate tariffs."""
    
    # Common UK flat rate tariffs for comparison (p/kWh inc VAT)
    FLAT_RATE_COMPARISONS = {
        "price_cap": 24.50,  # Ofgem price cap (updated periodically)
        "fixed_average": 22.00,  # Typical fixed tariff
        "economy_7_day": 28.00,  # Economy 7 day rate
        "economy_7_night": 12.00,  # Economy 7 night rate (00:00-07:00)
    }
    
    def __init__(self, custom_flat_rate: float = None):
        """Initialize with optional custom flat rate."""
        self.custom_flat_rate = custom_flat_rate
    
    def calculate_daily_savings(
        self,
        usage_records: list[dict],
        flat_rate: float = None
    ) -> dict:
        """
        Calculate savings for a day's usage.
        
        Args:
            usage_records: List of dicts with 'kwh' and 'rate' keys
            flat_rate: The flat rate to compare against (p/kWh)
        
        Returns:
            Dict with cost comparisons and savings
        """
        if flat_rate is None:
            flat_rate = self.custom_flat_rate or self.FLAT_RATE_COMPARISONS["price_cap"]
        
        total_kwh = sum(r.get("kwh", 0) for r in usage_records)
        agile_cost = sum(r.get("kwh", 0) * r.get("rate", 0) for r in usage_records)
        flat_cost = total_kwh * flat_rate
        
        savings = flat_cost - agile_cost
        savings_percent = (savings / flat_cost * 100) if flat_cost > 0 else 0
        
        return {
            "total_kwh": round(total_kwh, 3),
            "agile_cost_pence": round(agile_cost, 2),
            "agile_cost_pounds": round(agile_cost / 100, 2),
            "flat_rate_used": flat_rate,
            "flat_cost_pence": round(flat_cost, 2),
            "flat_cost_pounds": round(flat_cost / 100, 2),
            "savings_pence": round(savings, 2),
            "savings_pounds": round(savings / 100, 2),
            "savings_percent": round(savings_percent, 1),
            "effective_rate": round(agile_cost / total_kwh, 2) if total_kwh > 0 else 0,
        }
    
    def estimate_daily_cost(
        self,
        rates: list[dict],
        usage_profile: dict[int, float] = None,
        daily_kwh: float = 10.0
    ) -> dict:
        """
        Estimate daily cost based on rates and usage profile.
        
        Args:
            rates: List of rate slots with valid_from, valid_to, value_inc_vat
            usage_profile: Dict mapping hour (0-23) to relative usage weight
            daily_kwh: Total daily kWh consumption
        
        Returns:
            Dict with estimated costs
        """
        # Default flat usage profile
        if usage_profile is None:
            usage_profile = {h: 1.0 for h in range(24)}
        
        # Normalize weights
        total_weight = sum(usage_profile.values())
        normalized = {h: w / total_weight for h, w in usage_profile.items()}
        
        # Calculate hourly kWh
        hourly_kwh = {h: daily_kwh * w for h, w in normalized.items()}
        
        # Map rates to hours and calculate costs
        estimated_cost = 0.0
        for slot in rates:
            slot_hour = slot["valid_from"].astimezone(LONDON_TZ).hour
            # Calculate actual slot duration in hours
            slot_duration_hours = (slot["valid_to"] - slot["valid_from"]).total_seconds() / 3600
            slots_per_hour = 1.0 / slot_duration_hours if slot_duration_hours > 0 else 2
            slot_kwh = hourly_kwh.get(slot_hour, 0) / slots_per_hour
            estimated_cost += slot_kwh * slot["value_inc_vat"]
        
        flat_rate = self.custom_flat_rate or self.FLAT_RATE_COMPARISONS["price_cap"]
        flat_cost = daily_kwh * flat_rate
        
        return {
            "estimated_cost_pence": round(estimated_cost, 2),
            "estimated_cost_pounds": round(estimated_cost / 100, 2),
            "flat_rate_cost_pence": round(flat_cost, 2),
            "flat_rate_cost_pounds": round(flat_cost / 100, 2),
            "potential_savings_pence": round(flat_cost - estimated_cost, 2),
            "potential_savings_pounds": round((flat_cost - estimated_cost) / 100, 2),
            "daily_kwh": daily_kwh,
        }


class ExportOptimizer:
    """Optimize solar export vs storage decisions."""
    
    def __init__(
        self,
        export_rate: float = 15.0,  # p/kWh for export (SEG rate)
        battery_efficiency: float = 0.9,  # Round-trip efficiency
        battery_capacity_kwh: float = 10.0,
    ):
        """Initialize export optimizer."""
        self.export_rate = export_rate
        self.battery_efficiency = battery_efficiency
        self.battery_capacity_kwh = battery_capacity_kwh
    
    def analyze_export_windows(
        self,
        rates: list[dict],
        generation_forecast: dict[int, float] = None
    ) -> dict:
        """
        Analyze best times to export vs store.
        
        When import rate is low: Store (charge battery)
        When import rate is high: Use stored energy
        When import rate < export rate: Export (unusual but possible)
        
        Args:
            rates: List of rate slots
            generation_forecast: Expected solar generation by hour (kWh)
        
        Returns:
            Analysis with recommendations
        """
        recommendations = []
        export_windows = []
        store_windows = []
        
        for slot in rates:
            rate = slot["value_inc_vat"]
            slot_time = slot["valid_from"].astimezone(LONDON_TZ)
            hour = slot_time.hour
            
            # Logic:
            # - If rate is negative: DEFINITELY use power (you're paid to use it!)
            # - If rate < export_rate: Store/use, don't export
            # - If rate > export_rate: Consider exporting if you have excess
            # - High rates: Use battery instead of importing
            
            recommendation = {
                "time": slot["valid_from"].isoformat(),
                "hour": hour,
                "rate": rate,
            }
            
            if rate < 0:
                recommendation["action"] = "use_grid"
                recommendation["reason"] = "Negative pricing - maximize consumption"
                recommendation["priority"] = "critical"
                store_windows.append(slot)
            elif rate < self.export_rate * 0.8:
                recommendation["action"] = "charge_battery"
                recommendation["reason"] = f"Import rate ({rate:.1f}p) < export rate ({self.export_rate}p)"
                recommendation["priority"] = "high"
                store_windows.append(slot)
            elif rate > self.export_rate * 1.5:
                recommendation["action"] = "use_battery"
                recommendation["reason"] = f"High import rate ({rate:.1f}p) - avoid grid"
                recommendation["priority"] = "high"
            elif rate > self.export_rate:
                recommendation["action"] = "export_excess"
                recommendation["reason"] = f"Import rate ({rate:.1f}p) > export rate ({self.export_rate}p)"
                recommendation["priority"] = "medium"
                export_windows.append(slot)
            else:
                recommendation["action"] = "normal"
                recommendation["reason"] = "Standard operation"
                recommendation["priority"] = "low"
            
            recommendations.append(recommendation)
        
        # Calculate potential arbitrage value
        if store_windows and export_windows:
            avg_store_rate = sum(s["value_inc_vat"] for s in store_windows) / len(store_windows)
            avg_export_value = self.export_rate
            arbitrage_margin = (avg_export_value - avg_store_rate) * self.battery_efficiency
            
            potential_daily_arbitrage = arbitrage_margin * self.battery_capacity_kwh
        else:
            potential_daily_arbitrage = 0
        
        return {
            "recommendations": recommendations,
            "export_window_count": len(export_windows),
            "store_window_count": len(store_windows),
            "potential_arbitrage_pence": round(potential_daily_arbitrage, 2),
            "export_rate": self.export_rate,
            "battery_capacity_kwh": self.battery_capacity_kwh,
        }
    
    def find_best_charge_window(
        self,
        rates: list[dict],
        required_kwh: float,
        charge_rate_kw: float = 3.0
    ) -> dict:
        """
        Find the best window to charge battery.
        
        Args:
            rates: Available rate slots
            required_kwh: How much energy to store
            charge_rate_kw: Battery charge rate in kW
        
        Returns:
            Best charging window details
        """
        # Calculate required slots (30 min each)
        kwh_per_slot = charge_rate_kw * 0.5
        required_slots = int((required_kwh / kwh_per_slot) + 0.5)
        required_slots = max(1, min(required_slots, len(rates)))
        
        # Find cheapest consecutive window
        best_start_idx = 0
        best_cost = float("inf")
        
        for i in range(len(rates) - required_slots + 1):
            window_cost = sum(rates[j]["value_inc_vat"] for j in range(i, i + required_slots))
            if window_cost < best_cost:
                best_cost = window_cost
                best_start_idx = i
        
        best_window = rates[best_start_idx:best_start_idx + required_slots]
        
        return {
            "start_time": best_window[0]["valid_from"].isoformat(),
            "end_time": best_window[-1]["valid_to"].isoformat(),
            "slots": required_slots,
            "duration_minutes": required_slots * 30,
            "total_kwh": round(kwh_per_slot * required_slots, 2),
            "average_rate": round(best_cost / required_slots, 2),
            "total_cost_pence": round(best_cost * kwh_per_slot, 2),
        }


class UsagePatternAnalyzer:
    """Analyze and learn from usage patterns."""
    
    # Typical UK household usage patterns (relative weights by hour)
    TYPICAL_PROFILES = {
        "working_family": {
            0: 0.3, 1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.3,
            6: 0.8, 7: 1.2, 8: 1.0, 9: 0.5, 10: 0.4, 11: 0.4,
            12: 0.5, 13: 0.4, 14: 0.4, 15: 0.5, 16: 0.8, 17: 1.2,
            18: 1.5, 19: 1.4, 20: 1.3, 21: 1.2, 22: 0.8, 23: 0.5,
        },
        "home_worker": {
            0: 0.3, 1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.3,
            6: 0.6, 7: 0.9, 8: 1.0, 9: 1.2, 10: 1.2, 11: 1.1,
            12: 1.0, 13: 1.1, 14: 1.1, 15: 1.0, 16: 0.9, 17: 1.0,
            18: 1.2, 19: 1.1, 20: 1.0, 21: 0.9, 22: 0.6, 23: 0.4,
        },
        "retired": {
            0: 0.2, 1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.3,
            6: 0.5, 7: 0.8, 8: 1.0, 9: 1.1, 10: 1.2, 11: 1.1,
            12: 1.0, 13: 0.9, 14: 0.8, 15: 0.9, 16: 1.0, 17: 1.2,
            18: 1.3, 19: 1.2, 20: 1.0, 21: 0.8, 22: 0.5, 23: 0.3,
        },
        "ev_owner": {  # Assumes overnight charging
            0: 1.5, 1: 1.5, 2: 1.5, 3: 1.5, 4: 1.5, 5: 1.2,
            6: 0.8, 7: 1.0, 8: 0.8, 9: 0.5, 10: 0.4, 11: 0.4,
            12: 0.5, 13: 0.4, 14: 0.4, 15: 0.5, 16: 0.7, 17: 1.0,
            18: 1.3, 19: 1.2, 20: 1.1, 21: 1.0, 22: 0.8, 23: 1.2,
        },
        "flat": {  # Even distribution
            h: 1.0 for h in range(24)
        },
    }
    
    def __init__(self, profile_type: str = "working_family"):
        """Initialize with a usage profile type."""
        if profile_type not in self.TYPICAL_PROFILES:
            _LOGGER.warning(
                "Unknown usage profile '%s', falling back to 'working_family'. "
                "Valid profiles: %s",
                profile_type,
                list(self.TYPICAL_PROFILES.keys())
            )
            profile_type = "working_family"
        self.profile = self.TYPICAL_PROFILES[profile_type]
        self.profile_type = profile_type
        self.learned_adjustments: dict[int, float] = {}
    
    def get_profile(self) -> dict[int, float]:
        """Get the current usage profile with any learned adjustments."""
        profile = self.profile.copy()
        for hour, adjustment in self.learned_adjustments.items():
            if hour in profile:
                profile[hour] *= adjustment
        return profile
    
    def suggest_load_shift(
        self,
        rates: list[dict],
        load_kwh: float,
        duration_hours: float = 1.0,
        preferred_start: int = None,
        preferred_end: int = None,
    ) -> dict:
        """
        Suggest optimal time to run a load.
        
        Args:
            rates: Available rate slots
            load_kwh: Total energy for the load
            duration_hours: How long the load takes
            preferred_start: Earliest acceptable hour (0-23)
            preferred_end: Latest acceptable completion hour (0-23)
        
        Returns:
            Suggestion with timing and cost comparison
        """
        required_slots = max(1, int(duration_hours * 2))  # 30-min slots, minimum 1
        
        # Filter by preferred window if specified
        filtered_rates = rates
        if preferred_start is not None or preferred_end is not None:
            filtered_rates = []
            for slot in rates:
                hour = slot["valid_from"].astimezone(LONDON_TZ).hour
                if preferred_start is not None and hour < preferred_start:
                    continue
                if preferred_end is not None and hour >= preferred_end:
                    continue
                filtered_rates.append(slot)
        
        if len(filtered_rates) < required_slots:
            return {"error": "Not enough slots in preferred window"}
        
        # Find cheapest window
        best_idx = 0
        best_cost = float("inf")
        
        for i in range(len(filtered_rates) - required_slots + 1):
            window = filtered_rates[i:i + required_slots]
            # Check for continuity
            is_continuous = True
            for j in range(1, len(window)):
                if window[j]["valid_from"] != window[j-1]["valid_to"]:
                    is_continuous = False
                    break
            
            if is_continuous:
                cost = sum(s["value_inc_vat"] for s in window)
                if cost < best_cost:
                    best_cost = cost
                    best_idx = i
        
        best_window = filtered_rates[best_idx:best_idx + required_slots]
        
        # Calculate costs
        optimal_rate = best_cost / required_slots
        optimal_cost = load_kwh * optimal_rate
        
        # Compare to running now
        now = datetime.now(LONDON_TZ)
        current_slots = [s for s in rates if s["valid_from"].astimezone(LONDON_TZ).hour == now.hour]
        current_rate = current_slots[0]["value_inc_vat"] if current_slots else 25.0
        current_cost = load_kwh * current_rate
        
        # Compare to average
        avg_rate = sum(s["value_inc_vat"] for s in rates) / len(rates)
        avg_cost = load_kwh * avg_rate
        
        return {
            "recommended_start": best_window[0]["valid_from"].isoformat(),
            "recommended_end": best_window[-1]["valid_to"].isoformat(),
            "optimal_rate": round(optimal_rate, 2),
            "optimal_cost_pence": round(optimal_cost, 2),
            "current_rate": round(current_rate, 2),
            "current_cost_pence": round(current_cost, 2),
            "savings_vs_now_pence": round(current_cost - optimal_cost, 2),
            "average_rate": round(avg_rate, 2),
            "average_cost_pence": round(avg_cost, 2),
            "savings_vs_average_pence": round(avg_cost - optimal_cost, 2),
            "load_kwh": load_kwh,
            "duration_hours": duration_hours,
        }
    
    def analyze_rates_by_profile(
        self,
        rates: list[dict],
        daily_kwh: float = 10.0
    ) -> dict:
        """
        Analyze how current rates interact with usage profile.
        
        Returns insights about peak/off-peak alignment.
        """
        profile = self.get_profile()
        total_weight = sum(profile.values())
        
        # Group rates by hour
        hourly_rates = {}
        for slot in rates:
            hour = slot["valid_from"].astimezone(LONDON_TZ).hour
            if hour not in hourly_rates:
                hourly_rates[hour] = []
            hourly_rates[hour].append(slot["value_inc_vat"])
        
        # Average rate per hour
        avg_hourly = {h: sum(r)/len(r) for h, r in hourly_rates.items()}
        
        # Calculate weighted cost (what you'd pay with this profile)
        weighted_cost = 0.0
        for hour, rate in avg_hourly.items():
            weight = profile.get(hour, 1.0) / total_weight
            hourly_kwh = daily_kwh * weight
            # Each hour has 2 slots typically
            weighted_cost += hourly_kwh * rate
        
        # Calculate if profile aligns well with cheap rates
        # Find cheapest and most expensive hours
        sorted_hours = sorted(avg_hourly.items(), key=lambda x: x[1])
        cheapest_hours = [h for h, _ in sorted_hours[:6]]
        expensive_hours = [h for h, _ in sorted_hours[-6:]]
        
        # Check alignment
        usage_in_cheap = sum(profile.get(h, 0) for h in cheapest_hours)
        usage_in_expensive = sum(profile.get(h, 0) for h in expensive_hours)
        
        total_profile = sum(profile.values())
        cheap_alignment = usage_in_cheap / total_profile if total_profile > 0 else 0
        expensive_alignment = usage_in_expensive / total_profile if total_profile > 0 else 0
        
        # Optimization score (higher = better aligned with cheap rates)
        optimization_score = (cheap_alignment - expensive_alignment + 1) / 2 * 100
        
        return {
            "profile_type": self.profile_type,
            "daily_kwh": daily_kwh,
            "estimated_cost_pence": round(weighted_cost, 2),
            "cheapest_hours": cheapest_hours,
            "expensive_hours": expensive_hours,
            "usage_in_cheap_hours_percent": round(cheap_alignment * 100, 1),
            "usage_in_expensive_hours_percent": round(expensive_alignment * 100, 1),
            "optimization_score": round(optimization_score, 1),
            "recommendations": self._generate_recommendations(
                cheap_alignment, expensive_alignment, cheapest_hours, expensive_hours
            ),
        }
    
    def _generate_recommendations(
        self,
        cheap_alignment: float,
        expensive_alignment: float,
        cheapest_hours: list[int],
        expensive_hours: list[int]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs = []
        
        if expensive_alignment > 0.35:
            recs.append(
                f"High usage during expensive hours ({expensive_hours}). "
                "Consider shifting flexible loads to cheaper periods."
            )
        
        if cheap_alignment < 0.2:
            cheap_range = f"{min(cheapest_hours):02d}:00-{max(cheapest_hours)+1:02d}:00"
            recs.append(
                f"Low usage during cheapest hours ({cheap_range}). "
                "Schedule dishwasher, washing machine, or EV charging here."
            )
        
        # Check for overnight cheap rates
        overnight_cheap = any(h in cheapest_hours for h in [0, 1, 2, 3, 4, 5])
        if overnight_cheap:
            recs.append(
                "Overnight rates are cheap. Consider timer-controlled heating, "
                "EV charging, or battery storage."
            )
        
        # Check for evening peak
        evening_peak = any(h in expensive_hours for h in [17, 18, 19, 20])
        if evening_peak:
            recs.append(
                "Evening peak pricing detected (17:00-21:00). "
                "Pre-heat home, pre-cook meals, or use battery storage during this period."
            )
        
        if not recs:
            recs.append("Your usage profile is well-aligned with cheap rate periods!")
        
        return recs
