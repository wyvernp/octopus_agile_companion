DOMAIN = "octopus_agile_companion"
CONF_API_KEY = "api_key"
CONF_TARIFF_CODE = "tariff_code"
CONF_PRODUCT_CODE = "product_code"
CONF_CONSECUTIVE_PERIODS = "consecutive_periods"
CONF_FETCH_WINDOW_START = "fetch_window_start"
CONF_FETCH_WINDOW_END = "fetch_window_end"
CONF_CHEAP_THRESHOLD = "cheap_threshold"
CONF_EXPENSIVE_THRESHOLD = "expensive_threshold"

DEFAULT_FETCH_WINDOW_START = "16:00"
DEFAULT_FETCH_WINDOW_END = "20:00"
DEFAULT_CONSECUTIVE_PERIODS = [30, 60, 120, 180]  # Default periods in minutes
DEFAULT_CHEAP_THRESHOLD = 10.0  # p/kWh - considered cheap below this
DEFAULT_EXPENSIVE_THRESHOLD = 30.0  # p/kWh - considered expensive above this

DATA_COORDINATOR = "coordinator"
EXPECTED_SLOTS_PER_DAY = 48  # 48 half-hour slots in a day

# Event types
EVENT_CHEAP_PERIOD_START = f"{DOMAIN}_cheap_period_starting"
EVENT_EXPENSIVE_PERIOD_START = f"{DOMAIN}_expensive_period_starting"
EVENT_NEGATIVE_PERIOD_START = f"{DOMAIN}_negative_period_starting"
EVENT_RATES_UPDATED = f"{DOMAIN}_rates_updated"

# Attribution
ATTRIBUTION = "Data provided by Octopus Energy"
