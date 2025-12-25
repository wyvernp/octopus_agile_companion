import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    BooleanSelector,
)
from .const import (
    DOMAIN, CONF_API_KEY, CONF_PRODUCT_CODE, CONF_TARIFF_CODE,
    CONF_CONSECUTIVE_PERIODS,
    CONF_FETCH_WINDOW_START, CONF_FETCH_WINDOW_END,
    CONF_CHEAP_THRESHOLD, CONF_EXPENSIVE_THRESHOLD,
    CONF_FLAT_RATE_COMPARISON, CONF_USAGE_PROFILE, CONF_DAILY_KWH,
    CONF_EXPORT_RATE, CONF_BATTERY_CAPACITY, CONF_ENABLE_CARBON,
    DEFAULT_FETCH_WINDOW_START, DEFAULT_FETCH_WINDOW_END,
    DEFAULT_CONSECUTIVE_PERIODS, DEFAULT_CHEAP_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD,
    DEFAULT_FLAT_RATE, DEFAULT_USAGE_PROFILE, DEFAULT_DAILY_KWH,
    DEFAULT_EXPORT_RATE, DEFAULT_BATTERY_CAPACITY, DEFAULT_ENABLE_CARBON,
    USAGE_PROFILES,
)


def periods_to_str(periods):
    """Convert list of periods to comma-separated string."""
    return ",".join(str(p) for p in periods)


def str_to_periods(period_str):
    """Convert comma-separated string to list of periods."""
    parts = [p.strip() for p in period_str.split(",") if p.strip().isdigit()]
    if not parts:
        return DEFAULT_CONSECUTIVE_PERIODS
    return [int(p) for p in parts]


class OctopusAgileCompanionFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Octopus Agile Companion."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OctopusAgileOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            if not user_input[CONF_API_KEY].strip():
                errors["base"] = "api_key_missing"
            if not user_input[CONF_PRODUCT_CODE].strip():
                errors["base"] = errors.get("base") or "product_code_missing"
            if not user_input[CONF_TARIFF_CODE].strip():
                errors["base"] = errors.get("base") or "tariff_code_missing"

            if not errors:
                return self.async_create_entry(
                    title="Octopus Agile Companion",
                    data=user_input,
                    options={
                        CONF_CONSECUTIVE_PERIODS: DEFAULT_CONSECUTIVE_PERIODS,
                        CONF_CHEAP_THRESHOLD: DEFAULT_CHEAP_THRESHOLD,
                        CONF_EXPENSIVE_THRESHOLD: DEFAULT_EXPENSIVE_THRESHOLD,
                        CONF_FLAT_RATE_COMPARISON: DEFAULT_FLAT_RATE,
                        CONF_USAGE_PROFILE: DEFAULT_USAGE_PROFILE,
                        CONF_DAILY_KWH: DEFAULT_DAILY_KWH,
                        CONF_EXPORT_RATE: DEFAULT_EXPORT_RATE,
                        CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
                        CONF_ENABLE_CARBON: DEFAULT_ENABLE_CARBON,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_PRODUCT_CODE, default="AGILE-24-10-01"): str,
                    vol.Required(CONF_TARIFF_CODE, default="E-1R-AGILE-24-10-01-A"): str,
                    vol.Optional(
                        CONF_FETCH_WINDOW_START, default=DEFAULT_FETCH_WINDOW_START
                    ): str,
                    vol.Optional(
                        CONF_FETCH_WINDOW_END, default=DEFAULT_FETCH_WINDOW_END
                    ): str,
                }
            ),
            errors=errors,
        )


class OctopusAgileOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Octopus Agile Companion."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options - page 1: Basic settings."""
        if user_input is not None:
            # Store basic settings and move to analytics page
            self._basic_options = user_input
            return await self.async_step_analytics()

        current_options = self.config_entry.options
        current_periods = current_options.get(
            CONF_CONSECUTIVE_PERIODS, DEFAULT_CONSECUTIVE_PERIODS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CONSECUTIVE_PERIODS,
                        default=periods_to_str(current_periods),
                    ): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT,
                            multiline=False,
                        )
                    ),
                    vol.Optional(
                        CONF_FETCH_WINDOW_START,
                        default=current_options.get(
                            CONF_FETCH_WINDOW_START, DEFAULT_FETCH_WINDOW_START
                        ),
                    ): str,
                    vol.Optional(
                        CONF_FETCH_WINDOW_END,
                        default=current_options.get(
                            CONF_FETCH_WINDOW_END, DEFAULT_FETCH_WINDOW_END
                        ),
                    ): str,
                    vol.Optional(
                        CONF_CHEAP_THRESHOLD,
                        default=current_options.get(
                            CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=-50,
                            max=100,
                            step=0.5,
                            unit_of_measurement="p/kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_EXPENSIVE_THRESHOLD,
                        default=current_options.get(
                            CONF_EXPENSIVE_THRESHOLD, DEFAULT_EXPENSIVE_THRESHOLD
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=200,
                            step=0.5,
                            unit_of_measurement="p/kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )

    async def async_step_analytics(self, user_input=None):
        """Manage analytics options - page 2."""
        if user_input is not None:
            # Combine with basic options and save
            periods = str_to_periods(self._basic_options.get(CONF_CONSECUTIVE_PERIODS, ""))
            self._basic_options[CONF_CONSECUTIVE_PERIODS] = periods
            
            final_options = {**self._basic_options, **user_input}
            return self.async_create_entry(title="", data=final_options)

        current_options = self.config_entry.options

        return self.async_show_form(
            step_id="analytics",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_USAGE_PROFILE,
                        default=current_options.get(
                            CONF_USAGE_PROFILE, DEFAULT_USAGE_PROFILE
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=USAGE_PROFILES,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_DAILY_KWH,
                        default=current_options.get(
                            CONF_DAILY_KWH, DEFAULT_DAILY_KWH
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=100,
                            step=0.5,
                            unit_of_measurement="kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_FLAT_RATE_COMPARISON,
                        default=current_options.get(
                            CONF_FLAT_RATE_COMPARISON, DEFAULT_FLAT_RATE
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=0.1,
                            unit_of_measurement="p/kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_BATTERY_CAPACITY,
                        default=current_options.get(
                            CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=0.5,
                            unit_of_measurement="kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_EXPORT_RATE,
                        default=current_options.get(
                            CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=50,
                            step=0.1,
                            unit_of_measurement="p/kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_ENABLE_CARBON,
                        default=current_options.get(
                            CONF_ENABLE_CARBON, DEFAULT_ENABLE_CARBON
                        ),
                    ): BooleanSelector(),
                }
            ),
        )
