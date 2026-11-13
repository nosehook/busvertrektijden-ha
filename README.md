# HACS bus vertrektijden (fork)

A Home Assistant integration that displays upcoming bus departures in real time for a specific bus stop.

> **Fork** of [kerstenremco/busvertrektijden-ha](https://github.com/kerstenremco/busvertrektijden-ha) with departure sensors in minutes and as a time, and line + direction filters. It keeps the same domain (`busvertrektijden`), so it replaces the original installation and your existing stops, sensors and cards keep working.

Note: This integration only works for bus stops located in the Netherlands 🇳🇱.

## What's new in this fork (3.0.0)

- **Minutes and departure time**: for every stop there are two new sensors:
  - *Eerstvolgende bus over* — minutes until the next bus (`device_class: duration`, unit `min`), counting down locally between API calls;
  - *Eerstvolgende vertrektijd* — the expected departure time (`device_class: timestamp`), including delays.
- **Line + direction filters**: open the integration and click **Configure** to add filters such as *line 73 towards Zeist*. Each filter gets its own *… vertrek over* and *… vertrektijd* sensors. Lines and directions are picked from the departures at that stop (you can also type one). Filters can be removed again; their sensors are deleted.
- **Rich attributes** on the new sensors: line, direction, trip name, scheduled and expected time, delay in minutes, the next departures (minutes, time, delay, cancelled) and alerts.
- **Cancelled trips** are skipped for the minutes/time state but still listed (flagged) in the attributes.
- **One API call per stop per minute**, shared by all sensors of that stop.
- **Compatible**: the original *Bushalte …* sensor (seconds until the first departure, `stops` and `alerts` attributes) is unchanged; each stop also gets a `fetched_at` attribute and every departure an `expected_at` and `delay_minutes` field.
- Dutch translations.

## Installation

### Marketplace / HACS (custom repository)
1. If the original integration was installed through the Marketplace or HACS, remove that repository there (keep your configured stops).
2. Add `https://github.com/nosehook/busvertrektijden-ha` as a custom repository, category **Integration**, and install **Bus vertrektijden**.
3. Restart Home Assistant.

### Manual
Copy `custom_components/busvertrektijden` to `/config/custom_components/busvertrektijden` and restart Home Assistant.

Then add a stop under **Settings → Devices & services → Add integration → Bus vertrektijden**.

## Frontend card

The [Bushalte Card](https://github.com/nosehook/bushalte-card) shows a stop as a Dutch bus stop sign with line panels and live departure times. The original [Bustijden Card](https://github.com/kerstenremco/busvertrektijden-ha-card) keeps working too.

## Credits

Original integration by [@kerstenremco](https://github.com/kerstenremco). Data from busvertrektijden.nl.

## Contributing

Contributions are always welcome! Open a PR when needed!
