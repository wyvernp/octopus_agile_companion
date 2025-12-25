DOMAIN = "octopus_agile_companion"
CONF_API_KEY = "api_key"
CONF_TARIFF_CODE = "tariff_code"
CONF_PRODUCT_CODE = "product_code"
CONF_CONSECUTIVE_PERIODS = "consecutive_periods"
CONF_FETCH_WINDOW_START = "fetch_window_start"
CONF_FETCH_WINDOW_END = "fetch_window_end"
CONF_CHEAP_THRESHOLD = "cheap_threshold"
CONF_EXPENSIVE_THRESHOLD = "expensive_threshold"

# Analytics configuration
CONF_FLAT_RATE_COMPARISON = "flat_rate_comparison"
CONF_USAGE_PROFILE = "usage_profile"
CONF_DAILY_KWH = "daily_kwh"
CONF_EXPORT_RATE = "export_rate"
CONF_BATTERY_CAPACITY = "battery_capacity"
CONF_ENABLE_CARBON = "enable_carbon_tracking"
CONF_POSTCODE = "postcode"

DEFAULT_FETCH_WINDOW_START = "16:00"
DEFAULT_FETCH_WINDOW_END = "20:00"
DEFAULT_CONSECUTIVE_PERIODS = [30, 60, 120, 180]  # Default periods in minutes
DEFAULT_CHEAP_THRESHOLD = 10.0  # p/kWh - considered cheap below this
DEFAULT_EXPENSIVE_THRESHOLD = 30.0  # p/kWh - considered expensive above this

# Analytics defaults
DEFAULT_FLAT_RATE = 24.50  # Ofgem price cap rate p/kWh
DEFAULT_USAGE_PROFILE = "working_family"
DEFAULT_DAILY_KWH = 10.0
DEFAULT_EXPORT_RATE = 15.0  # SEG export rate p/kWh
DEFAULT_BATTERY_CAPACITY = 0.0  # No battery by default
DEFAULT_ENABLE_CARBON = True

# Usage profile options
USAGE_PROFILES = [
    "working_family",
    "home_worker",
    "retired",
    "ev_owner",
    "flat",
]

DATA_COORDINATOR = "coordinator"
EXPECTED_SLOTS_PER_DAY = 48  # 48 half-hour slots in a day

# Event types
EVENT_CHEAP_PERIOD_START = f"{DOMAIN}_cheap_period_starting"
EVENT_EXPENSIVE_PERIOD_START = f"{DOMAIN}_expensive_period_starting"
EVENT_NEGATIVE_PERIOD_START = f"{DOMAIN}_negative_period_starting"
EVENT_RATES_UPDATED = f"{DOMAIN}_rates_updated"

# Attribution
ATTRIBUTION = "Data provided by Octopus Energy"
