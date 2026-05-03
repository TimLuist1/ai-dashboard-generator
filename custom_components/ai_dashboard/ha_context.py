"""Collect full Home Assistant context for AI Assistant."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Attributes we include per entity to keep context compact
_RELEVANT_ATTRS = {
    "unit_of_measurement",
    "brightness",
    "color_temp",
    "rgb_color",
    "current_temperature",
    "target_temperature",
    "hvac_mode",
    "hvac_action",
    "hvac_modes",
    "media_title",
    "media_artist",
    "volume_level",
    "is_volume_muted",
    "position",
    "current_position",
    "battery_level",
    "supported_features",
    "device_class",
    "state_class",
    "options",
    "min",
    "max",
    "step",
}


class HAContextBuilder:
    """Builds a comprehensive, token-efficient snapshot of HA for AI consumption."""

    def __init__(self, hass: "HomeAssistant") -> None:
        self.hass = hass

    async def async_build(
        self,
        include_states: bool = True,
        max_entities: int = 300,
    ) -> dict:
        """Build and return a full HA context dict."""
        from homeassistant.helpers import area_registry as ar
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        area_reg = ar.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)

        # ── Areas ──────────────────────────────────────────────────
        areas = [
            {
                "id": a.id,
                "name": a.name,
                "icon": a.icon,
            }
            for a in area_reg.async_list_areas()
        ]

        # ── Device → area mapping ──────────────────────────────────
        device_area: dict[str, str] = {
            d.id: d.area_id
            for d in device_reg.devices.values()
            if d.area_id
        }

        # ── Entities ───────────────────────────────────────────────
        entities: list[dict] = []
        for entry in list(entity_reg.entities.values())[:max_entities]:
            state = self.hass.states.get(entry.entity_id)
            if state is None:
                continue

            area_id = entry.area_id or device_area.get(entry.device_id or "")
            area_name: str | None = None
            if area_id:
                area_obj = area_reg.async_get_area(area_id)
                area_name = area_obj.name if area_obj else None

            entity_info: dict[str, Any] = {
                "entity_id": entry.entity_id,
                "domain": entry.entity_id.split(".")[0],
                "name": state.attributes.get("friendly_name") or entry.name or entry.entity_id,
                "state": state.state,
                "area_id": area_id,
                "area": area_name,
                "device_class": state.attributes.get("device_class") or entry.device_class,
                "disabled": entry.disabled,
            }

            if include_states:
                attrs = {
                    k: v
                    for k, v in state.attributes.items()
                    if k in _RELEVANT_ATTRS
                }
                if attrs:
                    entity_info["attributes"] = attrs

            entities.append(entity_info)

        # ── Automations ────────────────────────────────────────────
        automations = [
            {
                "entity_id": s.entity_id,
                "name": s.attributes.get("friendly_name", s.entity_id),
                "state": s.state,
                "last_triggered": s.attributes.get("last_triggered"),
            }
            for s in self.hass.states.async_all("automation")
        ]

        # ── Scenes ─────────────────────────────────────────────────
        scenes = [
            {
                "entity_id": s.entity_id,
                "name": s.attributes.get("friendly_name", s.entity_id),
            }
            for s in self.hass.states.async_all("scene")
        ]

        # ── Scripts ────────────────────────────────────────────────
        scripts = [
            {
                "entity_id": s.entity_id,
                "name": s.attributes.get("friendly_name", s.entity_id),
                "state": s.state,
            }
            for s in self.hass.states.async_all("script")
        ]

        # ── HA Config ──────────────────────────────────────────────
        # hass.config.units.name was removed in HA 2024.x; use system string
        units = self.hass.config.units
        unit_system_name = (
            getattr(units, "name", None)
            or getattr(units, "SYSTEM_METRIC", None)
            or ("metric" if getattr(units, "is_metric", True) else "imperial")
        )
        config_info = {
            "location_name": self.hass.config.location_name,
            "unit_system": unit_system_name,
            "time_zone": str(self.hass.config.time_zone),
            "country": getattr(self.hass.config, "country", None),
            "language": getattr(self.hass.config, "language", "de"),
            "version": self.hass.data.get("homeassistant_version", "unknown"),
        }

        return {
            "config": config_info,
            "areas": areas,
            "entities": entities,
            "automations": automations,
            "scenes": scenes,
            "scripts": scripts,
            "entity_count": len(entities),
            "area_count": len(areas),
        }

    def build_compact_summary(self, context: dict) -> str:
        """Build a compact text summary optimised for AI token usage."""
        lines: list[str] = []

        cfg = context.get("config", {})
        lines.append(
            f"# Home Assistant – {cfg.get('location_name', 'Mein Zuhause')}"
        )
        lines.append(
            f"Zeitzone: {cfg.get('time_zone', '?')} | "
            f"Einheiten: {cfg.get('unit_system', '?')} | "
            f"Sprache: {cfg.get('language', '?')}"
        )
        lines.append("")

        # Areas
        lines.append(f"## Bereiche ({len(context['areas'])})")
        for a in context["areas"]:
            lines.append(f"  id={a['id']}  name=\"{a['name']}\"")
        lines.append("")

        # Entities grouped by area
        lines.append(f"## Entities ({len(context['entities'])})")
        by_area: dict[str, list[dict]] = {}
        for e in context["entities"]:
            if e.get("disabled"):
                continue
            key = e.get("area") or "_kein_bereich"
            by_area.setdefault(key, []).append(e)

        for area_name in sorted(by_area):
            lines.append(f"\n### {area_name}")
            for e in sorted(by_area[area_name], key=lambda x: x["domain"]):
                state_str = e["state"]
                attrs = e.get("attributes", {})
                unit = attrs.get("unit_of_measurement", "")
                if unit:
                    state_str += f" {unit}"
                dc = e.get("device_class") or ""
                lines.append(
                    f"  {e['entity_id']} | \"{e['name']}\" | {e['domain']}"
                    + (f" [{dc}]" if dc else "")
                    + f" → {state_str}"
                )
        lines.append("")

        # Automations (abbreviated)
        if context["automations"]:
            lines.append(f"## Automationen ({len(context['automations'])})")
            for a in context["automations"][:30]:
                lines.append(
                    f"  {a['entity_id']} | \"{a['name']}\" | {a['state']}"
                )
            lines.append("")

        # Scenes (abbreviated)
        if context["scenes"]:
            lines.append(f"## Szenen ({len(context['scenes'])})")
            for s in context["scenes"][:15]:
                lines.append(f"  {s['entity_id']} | \"{s['name']}\"")
            lines.append("")

        # Scripts (abbreviated)
        if context["scripts"]:
            lines.append(f"## Skripte ({len(context['scripts'])})")
            for s in context["scripts"][:10]:
                lines.append(f"  {s['entity_id']} | \"{s['name']}\" | {s['state']}")

        return "\n".join(lines)
