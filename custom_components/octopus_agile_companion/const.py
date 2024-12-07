DOMAIN = "octopus_agile_companion"
CONF_API_KEY = "api_key"
CONF_TARIFF_CODE = "tariff_code"
CONF_PRODUCT_CODE = "product_code"
CONF_CONSECUTIVE_PERIODS = "consecutive_periods"
CONF_FETCH_WINDOW_START = "fetch_window_start"
CONF_FETCH_WINDOW_END = "fetch_window_end"

DEFAULT_FETCH_WINDOW_START = "16:00"
DEFAULT_FETCH_WINDOW_END = "20:00"
DEFAULT_CONSECUTIVE_PERIODS = [30, 60, 120, 180]  # Default periods in minutes

DATA_COORDINATOR = "coordinator"
EXPECTED_SLOTS_PER_DAY = 48  # 48 half-hour slots in a day
