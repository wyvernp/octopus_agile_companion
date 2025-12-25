# Octopus Agile Companion

A Home Assistant custom integration for Octopus Energy Agile tariff users. Get real-time electricity pricing, find the cheapest time windows, and automate your energy usage.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

## Features

### Real-Time Rate Monitoring
- **Current Rate Sensor** - Shows current p/kWh with rich attributes including:
  - Next rate and time
  - Minutes remaining in current slot
  - Daily min/max/average
  - Rate status (negative, very_cheap, cheap, normal, expensive, very_expensive)
- **Next Rate Sensor** - Preview upcoming rate with countdown

### Daily Statistics
- Today's average, minimum, and maximum rates
- Tomorrow's average rate (when available after ~4pm)

### Cheapest Window Detection
For each configured period (default: 30, 60, 120, 180 minutes):
- **Today/Tomorrow Cheapest Window Start** - Timestamp sensors showing optimal usage times
- **Cheapest Window Cost** - Average p/kWh for each window
- **Window Active Binary Sensor** - Turns ON during the cheapest window (perfect for automations!)

### Threshold-Based Alerts
- **Currently Cheap** - Binary sensor ON when rate is below your configured threshold
- **Currently Expensive** - Binary sensor ON when rate is above your threshold
- **Currently Negative** - Binary sensor ON when you're being PAID to use electricity!
- Configurable thresholds via Number entities in the UI

### Negative Pricing Detection
- Binary sensors indicating if today/tomorrow has any negative pricing periods
- Attributes show exactly when and how negative

### Services for Automations
Call these services in scripts and automations with response data:

| Service | Description |
|---------|-------------|
| `octopus_agile_companion.get_rates` | Get all rates for a date |
| `octopus_agile_companion.get_cheapest_slots` | Find N cheapest slots (consecutive or individual) |
| `octopus_agile_companion.get_expensive_slots` | Find N most expensive slots |

### Events
The integration fires events you can trigger automations from:
- `octopus_agile_companion_rates_updated` - When new rate data is fetched

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Click the three dots menu → Custom repositories
3. Add `https://github.com/wyvernp/octopus_agile_companion` as an Integration
4. Search for "Octopus Agile Companion" and install
5. Restart Home Assistant

### Manual
1. Download the latest release
2. Copy `custom_components/octopus_agile_companion` to your `config/custom_components/`
3. Restart Home Assistant

## Configuration

### Initial Setup
1. Go to Settings → Devices & Services → Add Integration
2. Search for "Octopus Agile Companion"
3. Enter your:
   - **API Key** - From [Octopus Developer Dashboard](https://octopus.energy/dashboard/developer/)
   - **Product Code** - e.g., `AGILE-24-10-01`
   - **Tariff Code** - e.g., `E-1R-AGILE-24-10-01-A` (check your account)
   - **Fetch Window** - When to fetch tomorrow's rates (default 16:00-20:00)

### Options (Reconfigurable Anytime)
Click "Configure" on the integration to change:
- **Consecutive Periods** - Comma-separated minutes (e.g., `30,60,120,180`)
- **Cheap Threshold** - Rate below this triggers "Currently Cheap"
- **Expensive Threshold** - Rate above this triggers "Currently Expensive"
- **Fetch Window** - Adjust when data is fetched

You can also adjust thresholds directly via the Number entities in the UI!

## Example Automations

### Run Appliance During Cheapest 60min Window
```yaml
automation:
  - alias: "Dishwasher during cheap window"
    trigger:
      - platform: state
        entity_id: binary_sensor.octopus_agile_cheapest_60min_window_active
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.dishwasher
```

### Notify When Rate Goes Negative
```yaml
automation:
  - alias: "Negative rate alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.octopus_agile_currently_negative_rate
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "🎉 Negative Electricity Rate!"
          message: "You're being PAID to use electricity! Current rate: {{ states('sensor.octopus_agile_current_rate') }}p/kWh"
```

### Avoid Expensive Periods
```yaml
automation:
  - alias: "Pause charging when expensive"
    trigger:
      - platform: state
        entity_id: binary_sensor.octopus_agile_currently_expensive_rate
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ev_charger
```

### Use Service to Find Best Slots
```yaml
script:
  find_best_charging_time:
    sequence:
      - service: octopus_agile_companion.get_cheapest_slots
        data:
          num_slots: 4
          consecutive: true
        response_variable: result
      - service: notify.mobile_app
        data:
          message: "Best 2-hour window starts at {{ result.slots[0].valid_from }}"
```

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.octopus_agile_current_rate` | Sensor | Current rate in p/kWh |
| `sensor.octopus_agile_next_rate` | Sensor | Next slot rate |
| `sensor.octopus_agile_today_average_rate` | Sensor | Today's average |
| `sensor.octopus_agile_today_minimum_rate` | Sensor | Today's lowest rate |
| `sensor.octopus_agile_today_maximum_rate` | Sensor | Today's highest rate |
| `sensor.octopus_agile_tomorrow_average_rate` | Sensor | Tomorrow's average |
| `sensor.octopus_agile_today_cheapest_Xmin_window` | Sensor | Cheapest window start (per period) |
| `sensor.octopus_agile_tomorrow_cheapest_Xmin_window` | Sensor | Tomorrow's cheapest window |
| `sensor.octopus_agile_today_cheapest_Xmin_cost` | Sensor | Average rate of window |
| `binary_sensor.octopus_agile_cheapest_Xmin_window_active` | Binary | ON during cheapest window |
| `binary_sensor.octopus_agile_today_has_negative_pricing` | Binary | Any negative slots today |
| `binary_sensor.octopus_agile_tomorrow_has_negative_pricing` | Binary | Any negative slots tomorrow |
| `binary_sensor.octopus_agile_currently_negative_rate` | Binary | Current rate < 0 |
| `binary_sensor.octopus_agile_currently_cheap_rate` | Binary | Below cheap threshold |
| `binary_sensor.octopus_agile_currently_expensive_rate` | Binary | Above expensive threshold |
| `number.octopus_agile_cheap_rate_threshold` | Number | Adjustable cheap threshold |
| `number.octopus_agile_expensive_rate_threshold` | Number | Adjustable expensive threshold |

## Support

- [GitHub Issues](https://github.com/wyvernp/octopus_agile_companion/issues)
- [GitHub Discussions](https://github.com/wyvernp/octopus_agile_companion/discussions)

## License

MIT License - see [LICENSE](LICENSE) for details.