"""Entity analyzer for AI Dashboard Generator.

Fetches all entities from Home Assistant, groups them by area,
and applies smart filtering to remove irrelevant technical entities.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class EntityInfo:
    """Information about a single entity."""

    entity_id: str
    domain: str
    name: str
    friendly_name: str
    state: str
    attributes: dict[str, Any]
    device_class: str | None
    icon: str | None
    area_id: str | None
    area_name: str | None
    is_relevant: bool = True
    filter_reason: str | None = None
    suggested_name: str | None = None
    suggested_icon: str | None = None


@dataclass
class AreaInfo:
    """Information about an area with its entities."""

    area_id: str
    name: str
    icon: str
    entities: list[EntityInfo] = field(default_factory=list)
    entity_counts: dict[str, int] = field(default_factory=dict)


class EntityAnalyzer:
    """Analyzes all Home Assistant entities and groups them by area."""

    def __init__(self, hass: "HomeAssistant") -> None:
        """Initialize the analyzer."""
        self.hass = hass
        self._cache: dict[str, Any] | None = None
        self._cache_time: float = 0
        self._cache_ttl: float = 30.0  # 30 seconds cache

    async def async_get_areas_with_entities(self) -> list[dict[str, Any]]:
        """Get all areas with their entities, analyzed and filtered.

        Results are cached for 30 seconds to avoid repeated entity parsing.
        """
        import time
        now = time.monotonic()

        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            _LOGGER.debug("Returning cached entity analysis")
            return self._cache
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er
        from .const import (
            ALWAYS_EXCLUDE_DOMAINS,
            AREA_ICONS,
            DEFAULT_AREA_ICON,
            DEFAULT_INCLUDE_DOMAINS,
            DOMAIN_ICONS,
            FILTER_DEVICE_CLASSES,
            FILTER_PATTERNS,
            SENSOR_DEVICE_CLASS_ICONS,
        )
        device_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)

        # Build area lookup
        areas: dict[str, AreaInfo] = {}
        for area in area_reg.async_list_areas():
            icon = self._get_area_icon(area.name)
            areas[area.id] = AreaInfo(
                area_id=area.id,
                name=area.name,
                icon=area.icon or icon,
            )

        # Add "Unassigned" pseudo-area for entities without area
        areas["_unassigned"] = AreaInfo(
            area_id="_unassigned",
            name="Nicht zugewiesen",
            icon="mdi:help-circle",
        )

        # Build device->area mapping
        device_area: dict[str, str] = {}
        for device in device_reg.devices.values():
            if device.area_id:
                device_area[device.id] = device.area_id

        # Analyze all entities
        all_entities: list[EntityInfo] = []
        for entry in entity_reg.entities.values():
            entity_id = entry.entity_id
            domain = entity_id.split(".")[0]

            # Get current state
            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            # Determine area (entity > device > unassigned)
            area_id = entry.area_id
            if not area_id and entry.device_id:
                area_id = device_area.get(entry.device_id)
            if not area_id:
                area_id = "_unassigned"

            # Get friendly name
            friendly_name = (
                state.attributes.get("friendly_name")
                or entry.name
                or self._entity_id_to_name(entity_id)
            )

            # Get device class
            device_class = state.attributes.get("device_class") or entry.device_class

            # Get icon
            icon = state.attributes.get("icon") or entry.icon

            info = EntityInfo(
                entity_id=entity_id,
                domain=domain,
                name=entry.name or entity_id,
                friendly_name=friendly_name,
                state=state.state,
                attributes=dict(state.attributes),
                device_class=device_class,
                icon=icon,
                area_id=area_id,
                area_name=areas.get(area_id, areas["_unassigned"]).name,
            )

            # Apply filtering
            self._analyze_entity(info)

            # Generate suggested name and icon
            info.suggested_name = self._suggest_name(info, areas.get(area_id))
            info.suggested_icon = self._suggest_icon(info)

            all_entities.append(info)

        # Group by area
        for info in all_entities:
            area_id = info.area_id or "_unassigned"
            if area_id not in areas:
                area_id = "_unassigned"
            area = areas[area_id]
            area.entities.append(info)

            # Count by domain
            if info.is_relevant:
                area.entity_counts[info.domain] = (
                    area.entity_counts.get(info.domain, 0) + 1
                )

        # Build result, sort by area name, put unassigned last
        result = []
        sorted_areas = sorted(
            [a for a in areas.values() if a.area_id != "_unassigned"],
            key=lambda a: a.name.lower(),
        )

        unassigned = areas.get("_unassigned")
        if unassigned and unassigned.entities:
            sorted_areas.append(unassigned)

        for area in sorted_areas:
            relevant_entities = [e for e in area.entities if e.is_relevant]
            all_area_entities = area.entities

            result.append(
                {
                    "area_id": area.area_id,
                    "name": area.name,
                    "icon": area.icon,
                    "entity_counts": area.entity_counts,
                    "entities": [self._entity_to_dict(e) for e in relevant_entities],
                    "hidden_entities": [
                        self._entity_to_dict(e) for e in all_area_entities if not e.is_relevant
                    ],
                    "total_entities": len(all_area_entities),
                    "relevant_entities": len(relevant_entities),
                }
            )

        # Cache the result
        self._cache = result
        self._cache_time = time.monotonic()

        return result

    def _analyze_entity(self, info: EntityInfo) -> None:
        """Determine if an entity is relevant and should be shown."""
        entity_id = info.entity_id
        domain = info.domain

        # Always exclude certain domains
        if domain in ALWAYS_EXCLUDE_DOMAINS:
            info.is_relevant = False
            info.filter_reason = f"Domain '{domain}' ist standardmäßig ausgeblendet"
            return

        # Only include default domains
        if domain not in DEFAULT_INCLUDE_DOMAINS:
            info.is_relevant = False
            info.filter_reason = f"Domain '{domain}' nicht in der Standard-Liste"
            return

        # Check entity ID patterns
        entity_lower = entity_id.lower()
        for pattern in FILTER_PATTERNS:
            if pattern in entity_lower:
                info.is_relevant = False
                info.filter_reason = f"Technisches Entity (Pattern: {pattern})"
                return

        # Check device class filters
        if info.device_class in FILTER_DEVICE_CLASSES:
            info.is_relevant = False
            info.filter_reason = f"Technische Sensor-Klasse: {info.device_class}"
            return

        # Filter battery sensors (keep battery level/percentage, not voltage)
        if domain == "sensor" and "battery" in entity_lower:
            if any(p in entity_lower for p in ["voltage", "_v_", "_volt"]):
                info.is_relevant = False
                info.filter_reason = "Batterie-Spannung (technisch)"
                return

        # Filter if entity has 'hidden' attribute set
        if info.attributes.get("hidden", False):
            info.is_relevant = False
            info.filter_reason = "Entity ist als versteckt markiert"
            return

        # Filter entities that look like internal/technical IDs
        # e.g. sensor.abc123def456_something
        entity_name_part = entity_id.split(".", 1)[-1]
        if re.match(r"^[0-9a-f]{8,}_", entity_name_part):
            info.is_relevant = False
            info.filter_reason = "Sieht nach einer internen ID aus"
            return

        # Filter obviously technical sensors by name patterns
        technical_keywords = [
            "uptime", "boot_count", "restart", "reachable", "last_seen",
            "firmware", "config_entry", "integration", "module", "heap",
            "memory", "cpu_", "disk_", "network_", "load_", "swap_",
            "processor_", "ipv4", "ipv6", "mac_address",
        ]
        for kw in technical_keywords:
            if kw in entity_lower:
                info.is_relevant = False
                info.filter_reason = f"Technisches Entity ('{kw}')"
                return

        # Mark entity as relevant
        info.is_relevant = True

    def _suggest_name(self, info: EntityInfo, area: AreaInfo | None) -> str:
        """Suggest a clean, user-friendly name for an entity."""
        current_name = info.friendly_name or info.name

        # Remove area prefix from name if it matches
        if area and area.name:
            name_lower = current_name.lower()
            area_lower = area.name.lower()
            if name_lower.startswith(area_lower):
                current_name = current_name[len(area.name):].strip(" -_")
            elif name_lower.startswith(area_lower.replace(" ", "_")):
                current_name = current_name[len(area_lower):].strip(" -_")

        # Capitalize and clean up
        if current_name:
            current_name = current_name.strip().replace("_", " ").title()

        # Add device class label if name is too generic
        generic_names = ["sensor", "switch", "light", "binary sensor", "input"]
        if current_name.lower() in generic_names and info.device_class:
            dc_names = {
                "temperature": "Temperatur",
                "humidity": "Luftfeuchtigkeit",
                "pressure": "Luftdruck",
                "illuminance": "Helligkeit",
                "motion": "Bewegungsmelder",
                "door": "Tür",
                "window": "Fenster",
                "co2": "CO₂",
                "pm25": "Feinstaub PM2.5",
                "pm10": "Feinstaub PM10",
                "battery": "Batterie",
                "energy": "Energie",
                "power": "Leistung",
                "smoke": "Rauchmelder",
                "gas": "Gas",
                "moisture": "Feuchtigkeit",
                "vibration": "Erschütterung",
                "sound": "Geräusch",
                "lock": "Schloss",
                "occupancy": "Anwesenheit",
                "plug": "Steckdose",
                "outlet": "Steckdose",
            }
            current_name = dc_names.get(info.device_class, current_name)

        return current_name or info.entity_id

    def _suggest_icon(self, info: EntityInfo) -> str:
        """Suggest an appropriate icon for an entity."""
        # Use existing icon if set
        if info.icon:
            return info.icon

        # Try device class specific icon
        if info.device_class:
            if info.device_class in SENSOR_DEVICE_CLASS_ICONS:
                return SENSOR_DEVICE_CLASS_ICONS[info.device_class]

        # Binary sensor specific icons
        if info.domain == "binary_sensor" and info.device_class:
            bs_icons = {
                "motion": "mdi:motion-sensor",
                "door": "mdi:door",
                "window": "mdi:window-open",
                "lock": "mdi:lock",
                "smoke": "mdi:smoke-detector",
                "gas": "mdi:gas-cylinder",
                "moisture": "mdi:water",
                "vibration": "mdi:vibrate",
                "sound": "mdi:volume-high",
                "occupancy": "mdi:home-account",
                "plug": "mdi:power-plug",
                "heat": "mdi:fire",
                "cold": "mdi:snowflake",
                "connectivity": "mdi:wifi",
                "battery": "mdi:battery",
                "tamper": "mdi:shield-alert",
                "problem": "mdi:alert-circle",
                "safety": "mdi:shield-check",
                "power": "mdi:flash",
                "presence": "mdi:home-account",
                "light": "mdi:brightness-5",
                "opening": "mdi:door-open",
            }
            if info.device_class in bs_icons:
                return bs_icons[info.device_class]

        # Fall back to domain icon
        return DOMAIN_ICONS.get(info.domain, "mdi:help-circle")

    def _get_area_icon(self, area_name: str) -> str:
        """Get an appropriate icon for an area based on its name."""
        name_lower = area_name.lower()
        for key, icon in AREA_ICONS.items():
            if key in name_lower:
                return icon
        return DEFAULT_AREA_ICON

    def _entity_id_to_name(self, entity_id: str) -> str:
        """Convert entity ID to human-readable name."""
        name_part = entity_id.split(".", 1)[-1]
        return name_part.replace("_", " ").title()

    def _entity_to_dict(self, info: EntityInfo) -> dict:
        """Convert EntityInfo to dict."""
        return {
            "entity_id": info.entity_id,
            "domain": info.domain,
            "friendly_name": info.friendly_name,
            "suggested_name": info.suggested_name,
            "suggested_icon": info.suggested_icon,
            "state": info.state,
            "device_class": info.device_class,
            "icon": info.icon,
            "area_id": info.area_id,
            "is_relevant": info.is_relevant,
            "filter_reason": info.filter_reason,
            "attributes": {
                k: v
                for k, v in info.attributes.items()
                if k not in ("friendly_name", "icon")
                and not isinstance(v, (list, dict))
                or k in ("unit_of_measurement", "device_class", "state_class")
            },
        }
