"""Dashboard generator for AI Dashboard Generator.

Generates a beautiful modern Lovelace dashboard configuration
based on entity analysis and AI suggestions.
Uses HA 2024.1+ sections view with Mushroom Cards for best appearance.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.lovelace import dashboard as lovelace_dashboard

from .const import (
    CONF_AI_PROVIDER,
    CONF_AI_MODEL,
    CONF_API_KEY,
    CONF_DASHBOARD_TITLE,
    CONF_DASHBOARD_URL_PATH,
    CONF_USE_MUSHROOM,
    CONF_LANGUAGE,
    AI_PROVIDER_OFFLINE,
    DASHBOARD_URL_PATH,
    DEFAULT_DASHBOARD_TITLE,
)

_LOGGER = logging.getLogger(__name__)


class DashboardGenerator:
    """Generates modern Lovelace dashboard configuration."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        options: dict,
    ) -> None:
        """Initialize the generator."""
        self.hass = hass
        self.config = config
        self.options = options
        self.use_mushroom = options.get(CONF_USE_MUSHROOM, True)
        self.language = options.get(CONF_LANGUAGE, "de")
        self.title = config.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE)
        self.url_path = config.get(CONF_DASHBOARD_URL_PATH, DASHBOARD_URL_PATH)

    async def async_generate(
        self,
        areas_data: list[dict],
        images: dict[str, str] | None = None,
        options: dict | None = None,
    ) -> dict:
        """Generate the complete dashboard configuration."""
        images = images or {}
        extra_options = options or {}

        _LOGGER.info(
            "Starting dashboard generation for %d areas", len(areas_data)
        )

        # Get AI enrichment if configured
        ai_data = await self._async_get_ai_enrichment(areas_data)

        # ── Main dashboard: overview only ────────────────────────────
        overview_view = self._build_overview_view(areas_data, ai_data, images)

        dashboard_config = {
            "title": self.title,
            "views": [overview_view],
        }

        # ── Per-room dashboards ─────────────────────────────────────
        room_dashboards: dict[str, dict] = {}
        for area in areas_data:
            if area["area_id"] == "_unassigned" and area["relevant_entities"] == 0:
                continue
            room_dashboards[area["area_id"]] = self._build_room_dashboard(
                area, ai_data, images
            )

        # Attach room configs for apply step (stripped before saving to HA)
        dashboard_config["_room_dashboards"] = room_dashboards  # type: ignore[assignment]

        _LOGGER.info(
            "Dashboard generation complete: main + %d room dashboards",
            len(room_dashboards),
        )
        return dashboard_config

    async def async_apply_dashboard(self, config: dict) -> None:
        """Apply the generated dashboard to Home Assistant."""
        from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN

        _LOGGER.info("Applying dashboard '%s' to Home Assistant", self.title)

        # Extract room dashboards without mutating the stored config
        room_dashboards: dict[str, dict] = config.get("_room_dashboards", {})  # type: ignore[assignment]
        # Strip internal keys for the Lovelace main config
        main_config = {k: v for k, v in config.items() if not k.startswith("_")}

        url_path = self.url_path

        try:
            # ── Apply main dashboard ────────────────────────────────
            await self._async_save_lovelace_dashboard(
                url_path=url_path,
                title=self.title,
                icon="mdi:robot-happy",
                show_in_sidebar=True,
                config=main_config,
            )
            _LOGGER.info("Applied main dashboard at /%s", url_path)

            # ── Apply per-room dashboards ───────────────────────────
            for area_id, room_config in room_dashboards.items():
                room_url = f"{url_path}-{area_id}"
                room_title = room_config.get("title", area_id)
                room_icon = room_config.get("_icon", "mdi:home-floor-1")
                # Strip internal metadata key before saving
                clean_room = {k: v for k, v in room_config.items() if not k.startswith("_")}
                await self._async_save_lovelace_dashboard(
                    url_path=room_url,
                    title=room_title,
                    icon=room_icon,
                    show_in_sidebar=False,
                    config=clean_room,
                )
                _LOGGER.info("Applied room dashboard at /%s", room_url)

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Failed to apply dashboard: %s", err)
            raise

    async def _async_save_lovelace_dashboard(
        self,
        url_path: str,
        title: str,
        icon: str,
        show_in_sidebar: bool,
        config: dict,
    ) -> None:
        """Create or update a Lovelace storage dashboard.

        Creating a dashboard requires two steps:
          1. Register the URL route + sidebar entry via DashboardsCollection
             (or frontend panel registration as fallback).
          2. Save the Lovelace config data to the storage object.

        Skipping step 1 leaves the URL unregistered → 404.
        """
        from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
        from homeassistant.components.frontend import async_register_built_in_panel

        lovelace_data = self.hass.data.get(LOVELACE_DOMAIN, {})
        dashboards: dict = lovelace_data.get("dashboards", {})

        if url_path not in dashboards:
            # ── Try to create via DashboardsCollection (preferred) ────────
            # This handles URL routing, sidebar entry, and metadata
            # persistence across HA restarts.
            collection = lovelace_data.get("dashboards_collection")
            if collection is not None:
                try:
                    await collection.async_create_item(
                        {
                            "url_path": url_path,
                            "title": title,
                            "icon": icon,
                            "show_in_sidebar": show_in_sidebar,
                            "require_admin": False,
                            "mode": "storage",
                        }
                    )
                    _LOGGER.info(
                        "Registered new Lovelace dashboard via collection: /%s",
                        url_path,
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "DashboardsCollection.async_create_item failed (%s),"
                        " falling back to manual panel registration",
                        err,
                    )

            if url_path not in dashboards:
                # ── Fallback: create storage object + register panel manually ─
                dash = lovelace_dashboard.LovelaceStorage(
                    self.hass,
                    {
                        "id": url_path,
                        "url_path": url_path,
                        "title": title,
                        "icon": icon,
                        "show_in_sidebar": show_in_sidebar,
                        "require_admin": False,
                        "mode": "storage",
                    },
                )
                dashboards[url_path] = dash
                try:
                    async_register_built_in_panel(
                        self.hass,
                        "lovelace",
                        sidebar_title=title if show_in_sidebar else None,
                        sidebar_icon=icon if show_in_sidebar else None,
                        frontend_url_path=url_path,
                        config={"mode": "storage"},
                        require_admin=False,
                        update=True,
                    )
                    _LOGGER.info(
                        "Registered new Lovelace dashboard via panel: /%s", url_path
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "async_register_built_in_panel failed for /%s: %s",
                        url_path,
                        err,
                    )

        # ── Save the Lovelace config data ──────────────────────────────────
        await dashboards[url_path].async_save(config)

    # ─────────────────────────────────────────────────────────────
    # Overview view
    # ─────────────────────────────────────────────────────────────

    def _build_overview_view(
        self, areas_data: list[dict], ai_data: dict, images: dict
    ) -> dict:
        """Build the main overview view."""
        is_de = self.language == "de"

        sections = []

        # Header section: greeting + weather + time
        header_section = self._build_header_section(areas_data, ai_data)
        sections.append(header_section)

        # Quick stats: persons, alarm, weather
        quick_section = self._build_quick_stats_section(areas_data)
        if quick_section:
            sections.append(quick_section)

        # Room navigation chips
        rooms_section = self._build_room_nav_section(areas_data, images)
        sections.append(rooms_section)

        # Lights on section
        lights_section = self._build_active_lights_section()
        if lights_section:
            sections.append(lights_section)

        # Climate overview
        climate_section = self._build_climate_overview_section(areas_data)
        if climate_section:
            sections.append(climate_section)

        return {
            "title": "Übersicht" if is_de else "Overview",
            "path": "overview",
            "icon": "mdi:home",
            "type": "sections",
            "max_columns": 4,
            "sections": sections,
        }

    def _build_header_section(self, areas_data: list[dict], ai_data: dict) -> dict:
        """Build the header section with greeting and weather."""
        is_de = self.language == "de"

        cards = []

        # Time/date card using mushroom template
        if self.use_mushroom:
            cards.append(
                {
                    "type": "custom:mushroom-template-card",
                    "primary": "{% set h = now().hour %}"
                    "{% if h < 6 %}🌙 Gute Nacht"
                    "{% elif h < 12 %}☀️ Guten Morgen"
                    "{% elif h < 18 %}🌤 Guten Tag"
                    "{% else %}🌆 Guten Abend{% endif %}"
                    if is_de
                    else "{% set h = now().hour %}"
                    "{% if h < 6 %}🌙 Good Night"
                    "{% elif h < 12 %}☀️ Good Morning"
                    "{% elif h < 18 %}🌤 Good Afternoon"
                    "{% else %}🌆 Good Evening{% endif %}",
                    "secondary": "{{ now().strftime('%A, %-d. %B %Y') }}"
                    if is_de
                    else "{{ now().strftime('%A, %B %-d, %Y') }}",
                    "icon": "mdi:home-heart",
                    "icon_color": "orange",
                    "tap_action": {"action": "none"},
                    "hold_action": {"action": "none"},
                }
            )
        else:
            cards.append(
                {
                    "type": "markdown",
                    "content": f"## 🏠 {self.title}\n**{{{{ now().strftime('%A, %-d. %B') }}}}**",
                }
            )

        # Weather card if weather entity exists
        weather_entities = self._find_entities_by_domain(areas_data, "weather")
        if weather_entities:
            weather_entity = weather_entities[0]["entity_id"]
            cards.append(
                {
                    "type": "weather-forecast",
                    "entity": weather_entity,
                    "forecast_type": "hourly",
                }
            )

        return {
            "type": "grid",
            "cards": cards,
            "column_span": 4,
        }

    def _build_quick_stats_section(self, areas_data: list[dict]) -> dict | None:
        """Build quick stats section with persons and important sensors."""
        cards = []

        # Person entities
        persons = self._find_entities_by_domain(areas_data, "person")
        for person in persons[:3]:
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-person-card",
                        "entity": person["entity_id"],
                        "layout": "vertical",
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "entity", "entity": person["entity_id"]})

        # Alarm panel
        alarms = self._find_entities_by_domain(areas_data, "alarm_control_panel")
        for alarm in alarms[:1]:
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-alarm-control-panel-card",
                        "entity": alarm["entity_id"],
                        "layout": "vertical",
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "alarm-panel", "entity": alarm["entity_id"]})

        if not cards:
            return None

        return {
            "type": "grid",
            "title": "Personen & Sicherheit" if self.language == "de" else "People & Security",
            "cards": cards,
            "column_span": 4,
        }

    def _build_room_nav_section(
        self, areas_data: list[dict], images: dict
    ) -> dict:
        """Build room navigation section with picture cards."""
        is_de = self.language == "de"
        cards = []

        for area in areas_data:
            if area["area_id"] == "_unassigned":
                continue

            entity_count = area.get("relevant_entities", 0)
            if entity_count == 0:
                continue

            entity_counts = area.get("entity_counts", {})
            subtitle_parts = []
            if entity_counts.get("light", 0):
                n = entity_counts["light"]
                subtitle_parts.append(f"{n} {'Licht' if (n == 1 and is_de) else 'Lichter' if is_de else 'light' if n == 1 else 'lights'}")
            if entity_counts.get("climate", 0):
                subtitle_parts.append("Heizung" if is_de else "Heating")
            if entity_counts.get("media_player", 0):
                subtitle_parts.append("TV/Audio")

            subtitle = " · ".join(subtitle_parts) if subtitle_parts else f"{entity_count} Geräte" if is_de else f"{entity_count} devices"

            image_url = images.get(area["area_id"])

            if self.use_mushroom:
                card: dict = {
                    "type": "custom:mushroom-template-card",
                    "primary": area["name"],
                    "secondary": subtitle,
                    "icon": area.get("icon", "mdi:home-floor-1"),
                    "icon_color": "blue",
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": f"/{self.url_path}-{area['area_id']}",
                    },
                    "fill_container": True,
                }
                if image_url:
                    card["picture"] = image_url
            else:
                card = {
                    "type": "button",
                    "name": area["name"],
                    "icon": area.get("icon", "mdi:home-floor-1"),
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": f"/{self.url_path}-{area['area_id']}",
                    },
                }

            cards.append(card)

        if not cards:
            return {
                "type": "grid",
                "title": "Räume" if is_de else "Rooms",
                "cards": [{"type": "markdown", "content": "Keine Räume gefunden." if is_de else "No rooms found."}],
            }

        return {
            "type": "grid",
            "title": "Räume" if is_de else "Rooms",
            "cards": cards,
            "column_span": 4,
        }

    def _build_active_lights_section(self) -> dict | None:
        """Build a section showing lights that are currently on."""
        if not self.use_mushroom:
            return None

        return {
            "type": "grid",
            "title": "Aktive Lichter" if self.language == "de" else "Active Lights",
            "cards": [
                {
                    "type": "custom:mushroom-chips-card",
                    "chips": [
                        {
                            "type": "template",
                            "icon": "mdi:lightbulb-group",
                            "icon_color": "{% if states.light | selectattr('state','eq','on') | list | count > 0 %}amber{% else %}grey{% endif %}",
                            "content": "{{ states.light | selectattr('state','eq','on') | list | count }} "
                            + ("an" if self.language == "de" else "on"),
                            "tap_action": {"action": "none"},
                        }
                    ],
                }
            ],
        }

    def _build_climate_overview_section(self, areas_data: list[dict]) -> dict | None:
        """Build climate overview across all areas."""
        climate_entities = self._find_entities_by_domain(areas_data, "climate")
        if not climate_entities:
            return None

        cards = []
        for entity in climate_entities[:6]:
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-climate-card",
                        "entity": entity["entity_id"],
                        "show_temperature_control": False,
                        "collapsible_controls": True,
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "thermostat", "entity": entity["entity_id"]})

        return {
            "type": "grid",
            "title": "Heizung" if self.language == "de" else "Climate",
            "cards": cards,
            "column_span": 4,
        }

    # ─────────────────────────────────────────────────────────────
    # Room dashboards (one standalone Lovelace dashboard per area)
    # ─────────────────────────────────────────────────────────────

    def _build_room_dashboard(
        self, area: dict, ai_data: dict, images: dict
    ) -> dict:
        """Build a standalone Lovelace dashboard config for one room."""
        area_id = area["area_id"]
        area_name = area["name"]
        area_icon = area.get("icon", "mdi:home-floor-1")
        is_de = self.language == "de"

        view = self._build_area_view(area, ai_data, images, back_url=f"/{self.url_path}")

        return {
            "title": area_name,
            "views": [view],
            # Internal metadata consumed by async_apply_dashboard
            "_icon": area_icon,
        }

    # ─────────────────────────────────────────────────────────────
    # Area (room) views
    # ─────────────────────────────────────────────────────────────

    def _build_area_view(
        self, area: dict, ai_data: dict, images: dict, back_url: str | None = None
    ) -> dict:
        """Build a complete view for one area/room."""
        area_id = area["area_id"]
        area_name = area["name"]
        area_icon = area.get("icon", "mdi:home-floor-1")
        image_url = images.get(area_id)

        entities = area.get("entities", [])

        # Get AI enrichment for this area
        area_ai = ai_data.get(area_id, {})

        sections = []

        # Back-navigation row (when rendered as standalone room dashboard)
        if back_url:
            back_label = "← Übersicht" if self.language == "de" else "← Overview"
            if self.use_mushroom:
                sections.append(
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "custom:mushroom-chips-card",
                                "chips": [
                                    {
                                        "type": "template",
                                        "icon": "mdi:arrow-left",
                                        "content": back_label,
                                        "tap_action": {
                                            "action": "navigate",
                                            "navigation_path": back_url,
                                        },
                                    }
                                ],
                            }
                        ],
                        "column_span": 4,
                    }
                )
            else:
                sections.append(
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "button",
                                "name": back_label,
                                "icon": "mdi:arrow-left",
                                "tap_action": {
                                    "action": "navigate",
                                    "navigation_path": back_url,
                                },
                            }
                        ],
                        "column_span": 4,
                    }
                )

        # Header section with image and title
        header = self._build_area_header(area, area_ai, image_url)
        sections.append(header)

        # Group entities by domain
        lights = [e for e in entities if e["domain"] == "light"]
        switches = [e for e in entities if e["domain"] == "switch"]
        climate = [e for e in entities if e["domain"] == "climate"]
        media_players = [e for e in entities if e["domain"] == "media_player"]
        covers = [e for e in entities if e["domain"] == "cover"]
        cameras = [e for e in entities if e["domain"] == "camera"]
        temp_sensors = [
            e for e in entities
            if e["domain"] == "sensor" and e.get("device_class") in ("temperature", "humidity", "pressure", "co2", "illuminance", "pm25", "pm10", "aqi")
        ]
        binary_sensors = [
            e for e in entities
            if e["domain"] == "binary_sensor"
        ]
        other_sensors = [
            e for e in entities
            if e["domain"] == "sensor" and e not in temp_sensors
        ]
        fans = [e for e in entities if e["domain"] == "fan"]
        vacuums = [e for e in entities if e["domain"] == "vacuum"]
        locks = [e for e in entities if e["domain"] == "lock"]
        others = [
            e for e in entities
            if e["domain"] in ("input_boolean", "input_number", "input_select", "number", "select")
        ]

        # Build sections by domain
        if lights:
            sections.append(self._build_lights_section(lights, area_ai))

        if climate:
            sections.append(self._build_climate_section(climate, area_ai))

        if media_players:
            sections.append(self._build_media_section(media_players, area_ai))

        if covers:
            sections.append(self._build_covers_section(covers, area_ai))

        if switches:
            sections.append(self._build_switches_section(switches, area_ai))

        if temp_sensors or binary_sensors:
            sections.append(
                self._build_sensors_section(
                    temp_sensors, binary_sensors, other_sensors, area_ai
                )
            )

        if cameras:
            sections.append(self._build_cameras_section(cameras, area_ai))

        if fans or vacuums:
            sections.append(self._build_appliances_section(fans, vacuums, locks, area_ai))

        if others:
            sections.append(self._build_controls_section(others, area_ai))

        if not sections[1:]:  # Only header
            sections.append(
                {
                    "type": "grid",
                    "cards": [
                        {
                            "type": "markdown",
                            "content": "Keine relevanten Geräte in diesem Raum." if self.language == "de" else "No relevant devices in this room.",
                        }
                    ],
                }
            )

        return {
            "title": area_name,
            "path": area_id,
            "icon": area_icon,
            "type": "sections",
            "max_columns": 4,
            "sections": sections,
            "id": area_id,
        }

    def _build_area_header(
        self, area: dict, area_ai: dict, image_url: str | None
    ) -> dict:
        """Build the header section for a room view."""
        cards = []

        if image_url:
            cards.append(
                {
                    "type": "picture",
                    "image": image_url,
                    "style": "height: 180px; object-fit: cover; border-radius: 12px;",
                }
            )

        if self.use_mushroom:
            entity_counts = area.get("entity_counts", {})
            subtitle_parts = []
            is_de = self.language == "de"

            if entity_counts.get("light"):
                n = entity_counts["light"]
                subtitle_parts.append(
                    f"{n} {'Licht' if n == 1 else 'Lichter'}" if is_de else f"{n} {'light' if n == 1 else 'lights'}"
                )
            if entity_counts.get("climate"):
                subtitle_parts.append("Heizung" if is_de else "Climate")
            if entity_counts.get("sensor"):
                n = entity_counts["sensor"]
                subtitle_parts.append(
                    f"{n} {'Sensor' if n == 1 else 'Sensoren'}" if is_de else f"{n} {'sensor' if n == 1 else 'sensors'}"
                )

            subtitle = (
                area_ai.get("hints", {}).get("subtitle")
                or " · ".join(subtitle_parts)
                or ""
            )

            cards.append(
                {
                    "type": "custom:mushroom-title-card",
                    "title": area["name"],
                    "subtitle": subtitle,
                    "title_tap_action": {"action": "none"},
                }
            )

        return {
            "type": "grid",
            "cards": cards,
            "column_span": 4,
        }

    def _build_lights_section(self, lights: list[dict], area_ai: dict) -> dict:
        """Build section for lights."""
        is_de = self.language == "de"
        cards = []

        for light in lights:
            name = self._get_entity_name(light, area_ai)
            icon = self._get_entity_icon(light, area_ai)

            if self.use_mushroom:
                card = {
                    "type": "custom:mushroom-light-card",
                    "entity": light["entity_id"],
                    "name": name,
                    "icon": icon,
                    "show_brightness_control": True,
                    "show_color_temp_control": True,
                    "collapsible_controls": True,
                    "fill_container": True,
                }
                # Add color control if light supports it
                if light.get("attributes", {}).get("supported_color_modes"):
                    modes = light["attributes"]["supported_color_modes"]
                    if isinstance(modes, list) and "hs" in modes or "rgb" in modes:
                        card["show_color_control"] = True
            else:
                card = {
                    "type": "light",
                    "entity": light["entity_id"],
                    "name": name,
                }
            cards.append(card)

        return {
            "type": "grid",
            "title": "Lichter" if is_de else "Lights",
            "cards": cards,
        }

    def _build_climate_section(self, climate: list[dict], area_ai: dict) -> dict:
        """Build section for climate entities."""
        is_de = self.language == "de"
        cards = []

        for entity in climate:
            name = self._get_entity_name(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-climate-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "show_temperature_control": True,
                        "collapsible_controls": True,
                        "fill_container": True,
                        "hvac_modes": ["off", "heat", "cool", "auto"],
                    }
                )
            else:
                cards.append({"type": "thermostat", "entity": entity["entity_id"]})

        return {
            "type": "grid",
            "title": "Heizung / Klima" if is_de else "Climate",
            "cards": cards,
        }

    def _build_media_section(self, media_players: list[dict], area_ai: dict) -> dict:
        """Build section for media players."""
        is_de = self.language == "de"
        cards = []

        for entity in media_players:
            name = self._get_entity_name(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-media-player-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "collapsible_controls": True,
                        "fill_container": True,
                        "media_controls": [
                            "on_off",
                            "shuffle",
                            "previous",
                            "play_pause_stop",
                            "next",
                            "repeat",
                        ],
                        "volume_controls": ["volume_mute", "volume_set", "volume_buttons"],
                    }
                )
            else:
                cards.append({"type": "media-control", "entity": entity["entity_id"]})

        return {
            "type": "grid",
            "title": "Medien" if is_de else "Media",
            "cards": cards,
        }

    def _build_covers_section(self, covers: list[dict], area_ai: dict) -> dict:
        """Build section for covers (blinds, shutters)."""
        is_de = self.language == "de"
        cards = []

        for entity in covers:
            name = self._get_entity_name(entity, area_ai)
            icon = self._get_entity_icon(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-cover-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "icon": icon,
                        "show_position_control": True,
                        "show_tilt_position_control": True,
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "entity", "entity": entity["entity_id"]})

        return {
            "type": "grid",
            "title": "Rollos / Jalousien" if is_de else "Covers & Blinds",
            "cards": cards,
        }

    def _build_switches_section(self, switches: list[dict], area_ai: dict) -> dict:
        """Build section for switches."""
        is_de = self.language == "de"
        cards = []

        for entity in switches:
            name = self._get_entity_name(entity, area_ai)
            icon = self._get_entity_icon(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-entity-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "icon": icon,
                        "tap_action": {"action": "toggle"},
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "button", "entity": entity["entity_id"], "name": name})

        return {
            "type": "grid",
            "title": "Schalter" if is_de else "Switches",
            "cards": cards,
        }

    def _build_sensors_section(
        self,
        temp_sensors: list[dict],
        binary_sensors: list[dict],
        other_sensors: list[dict],
        area_ai: dict,
    ) -> dict:
        """Build section for sensors."""
        is_de = self.language == "de"
        cards = []

        all_sensors = temp_sensors + binary_sensors + other_sensors[:5]

        for entity in all_sensors:
            name = self._get_entity_name(entity, area_ai)
            icon = self._get_entity_icon(entity, area_ai)

            if entity["domain"] == "binary_sensor":
                if self.use_mushroom:
                    cards.append(
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": entity["entity_id"],
                            "name": name,
                            "icon": icon,
                            "tap_action": {"action": "more-info"},
                            "fill_container": True,
                        }
                    )
                else:
                    cards.append(
                        {
                            "type": "entity",
                            "entity": entity["entity_id"],
                            "name": name,
                            "icon": icon,
                        }
                    )
            else:
                unit = entity.get("attributes", {}).get("unit_of_measurement", "")
                if self.use_mushroom:
                    cards.append(
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": entity["entity_id"],
                            "name": name,
                            "icon": icon,
                            "primary_info": "state",
                            "secondary_info": "last-changed",
                            "tap_action": {"action": "more-info"},
                            "fill_container": True,
                        }
                    )
                else:
                    cards.append(
                        {
                            "type": "entity",
                            "entity": entity["entity_id"],
                            "name": name,
                        }
                    )

        if not cards:
            return {"type": "grid", "cards": []}

        return {
            "type": "grid",
            "title": "Sensoren" if is_de else "Sensors",
            "cards": cards,
        }

    def _build_cameras_section(self, cameras: list[dict], area_ai: dict) -> dict:
        """Build section for cameras."""
        is_de = self.language == "de"
        cards = []

        for entity in cameras:
            name = self._get_entity_name(entity, area_ai)
            cards.append(
                {
                    "type": "picture-entity",
                    "entity": entity["entity_id"],
                    "name": name,
                    "show_name": True,
                    "show_state": False,
                    "camera_view": "auto",
                }
            )

        return {
            "type": "grid",
            "title": "Kameras" if is_de else "Cameras",
            "cards": cards,
            "column_span": 2,
        }

    def _build_appliances_section(
        self,
        fans: list[dict],
        vacuums: list[dict],
        locks: list[dict],
        area_ai: dict,
    ) -> dict:
        """Build section for appliances."""
        is_de = self.language == "de"
        cards = []

        for entity in fans:
            name = self._get_entity_name(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-fan-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "show_percentage_control": True,
                        "collapsible_controls": True,
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "entity", "entity": entity["entity_id"], "name": name})

        for entity in vacuums:
            name = self._get_entity_name(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-vacuum-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "entity", "entity": entity["entity_id"], "name": name})

        for entity in locks:
            name = self._get_entity_name(entity, area_ai)
            if self.use_mushroom:
                cards.append(
                    {
                        "type": "custom:mushroom-lock-card",
                        "entity": entity["entity_id"],
                        "name": name,
                        "fill_container": True,
                    }
                )
            else:
                cards.append({"type": "entity", "entity": entity["entity_id"], "name": name})

        return {
            "type": "grid",
            "title": "Geräte" if is_de else "Appliances",
            "cards": cards,
        }

    def _build_controls_section(self, others: list[dict], area_ai: dict) -> dict:
        """Build section for input helpers and controls."""
        is_de = self.language == "de"
        cards = []

        for entity in others:
            name = self._get_entity_name(entity, area_ai)
            icon = self._get_entity_icon(entity, area_ai)
            if entity["domain"] in ("input_boolean",):
                if self.use_mushroom:
                    cards.append(
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": entity["entity_id"],
                            "name": name,
                            "icon": icon,
                            "tap_action": {"action": "toggle"},
                            "fill_container": True,
                        }
                    )
                else:
                    cards.append({"type": "entity", "entity": entity["entity_id"]})
            else:
                cards.append(
                    {
                        "type": "entity",
                        "entity": entity["entity_id"],
                        "name": name,
                        "icon": icon,
                    }
                )

        return {
            "type": "grid",
            "title": "Steuerung" if is_de else "Controls",
            "cards": cards,
        }

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    async def _async_get_ai_enrichment(self, areas_data: list[dict]) -> dict:
        """Get AI enrichment for entities."""
        from .ai_provider import create_ai_provider

        provider_name = self.config.get(CONF_AI_PROVIDER, AI_PROVIDER_OFFLINE)
        api_key = self.config.get(CONF_API_KEY, "")
        model = self.config.get(CONF_AI_MODEL, "")

        provider = create_ai_provider(self.hass, provider_name, api_key, model)

        _LOGGER.debug("Using AI provider: %s", provider_name)

        try:
            entity_data = await provider.async_analyze_entities(areas_data, self.language)
            hints_data = await provider.async_generate_dashboard_hints(areas_data, self.language)

            # Merge into a unified dict keyed by area_id
            result = {}
            for area_id, ai_area in entity_data.items():
                result[area_id] = {
                    "icon": ai_area.get("icon"),
                    "color": ai_area.get("color"),
                    "entities": ai_area.get("entities", {}),
                    "hints": hints_data.get("areas", {}).get(area_id, {}),
                }

            return result
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("AI enrichment failed: %s – using defaults", err)
            return {}

    def _get_entity_name(self, entity: dict, area_ai: dict) -> str:
        """Get the best name for an entity."""
        entity_id = entity["entity_id"]
        ai_entities = area_ai.get("entities", {})
        if entity_id in ai_entities:
            ai_name = ai_entities[entity_id].get("friendly_name")
            if ai_name:
                return ai_name
        return entity.get("suggested_name") or entity.get("friendly_name") or entity_id

    def _get_entity_icon(self, entity: dict, area_ai: dict) -> str | None:
        """Get the best icon for an entity."""
        entity_id = entity["entity_id"]
        ai_entities = area_ai.get("entities", {})
        if entity_id in ai_entities:
            ai_icon = ai_entities[entity_id].get("icon")
            if ai_icon:
                return ai_icon
        return entity.get("suggested_icon") or entity.get("icon")

    def _find_entities_by_domain(
        self, areas_data: list[dict], domain: str
    ) -> list[dict]:
        """Find all entities with a given domain across all areas."""
        result = []
        for area in areas_data:
            for entity in area.get("entities", []):
                if entity["domain"] == domain:
                    result.append(entity)
        return result
