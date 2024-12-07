import voluptuous as vol
from homeassistant import config_entries
from .const import (
    DOMAIN, CONF_API_KEY, CONF_PRODUCT_CODE, CONF_TARIFF_CODE,
    CONF_CONSECUTIVE_PERIODS,
    CONF_FETCH_WINDOW_START, CONF_FETCH_WINDOW_END,
    DEFAULT_FETCH_WINDOW_START, DEFAULT_FETCH_WINDOW_END,
    DEFAULT_CONSECUTIVE_PERIODS
)

def periods_to_str(periods):
    return ",".join(str(p) for p in periods)

def str_to_periods(period_str):
    parts = [p.strip() for p in period_str.split(",") if p.strip().isdigit()]
    if not parts:
        return DEFAULT_CONSECUTIVE_PERIODS
    return [int(p) for p in parts]

class OctopusAgileCompanionFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input[CONF_API_KEY].strip():
                errors["base"] = "api_key_missing"
            if not user_input[CONF_PRODUCT_CODE].strip():
                errors["base"] = errors.get("base") or "product_code_missing"
            if not user_input[CONF_TARIFF_CODE].strip():
                errors["base"] = errors.get("base") or "tariff_code_missing"

            if not errors:
                return self.async_create_entry(title="Octopus Agile Companion", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_PRODUCT_CODE, default="AGILE-18-02-21"): str,
                    vol.Required(CONF_TARIFF_CODE, default="E-1R-AGILE-18-02-21-J"): str,
                    vol.Optional(CONF_FETCH_WINDOW_START, default=DEFAULT_FETCH_WINDOW_START): str,
                    vol.Optional(CONF_FETCH_WINDOW_END, default=DEFAULT_FETCH_WINDOW_END): str,
                }
            ),
            errors=errors
        )

    async def async_step_options(self, user_input=None):
        if user_input is not None:
            periods = str_to_periods(user_input.get(CONF_CONSECUTIVE_PERIODS, ""))
            user_input[CONF_CONSECUTIVE_PERIODS] = periods
            return self.async_create_entry(title="", data=user_input)

        current_periods = self.options.get(CONF_CONSECUTIVE_PERIODS, DEFAULT_CONSECUTIVE_PERIODS)
        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CONSECUTIVE_PERIODS, default=periods_to_str(current_periods)): str,
                    vol.Optional(CONF_FETCH_WINDOW_START, default=self.options.get(CONF_FETCH_WINDOW_START, DEFAULT_FETCH_WINDOW_START)): str,
                    vol.Optional(CONF_FETCH_WINDOW_END, default=self.options.get(CONF_FETCH_WINDOW_END, DEFAULT_FETCH_WINDOW_END)): str,
                }
            ),
            description_placeholders={
                "info": "Enter comma-separated periods in minutes (e.g., '30,60,120'). Ideally align with 30-min slots."
            }
        )
