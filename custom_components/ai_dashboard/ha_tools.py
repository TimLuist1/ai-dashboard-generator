"""Home Assistant tool definitions and executors for the AI Assistant.

Tools follow the OpenAI function-calling schema as the canonical format.
Helpers convert them to Anthropic / Google format on demand.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions  (OpenAI function-calling schema)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "call_service",
            "description": (
                "Ruft einen beliebigen Home Assistant Dienst auf. "
                "Damit kannst du Entities steuern: Licht an/aus/dimmen, "
                "Thermostat setzen, Medien steuern, Rolläden fahren, Schlösser bedienen, "
                "Automationen aktivieren/deaktivieren u.v.m."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": (
                            "Dienst-Domain, z.B. 'light', 'switch', 'climate', "
                            "'media_player', 'cover', 'lock', 'fan', 'vacuum', "
                            "'input_boolean', 'homeassistant', 'automation', 'scene'"
                        ),
                    },
                    "service": {
                        "type": "string",
                        "description": (
                            "Dienst-Name, z.B. 'turn_on', 'turn_off', 'toggle', "
                            "'set_temperature', 'set_hvac_mode', 'media_play_pause', "
                            "'set_cover_position', 'lock', 'unlock'"
                        ),
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "Ziel-Entity-ID (oder mehrere, kommagetrennt)",
                    },
                    "service_data": {
                        "type": "object",
                        "description": (
                            "Zusätzliche Parameter, z.B. "
                            "{'brightness_pct': 80, 'color_temp': 4000, "
                            "'temperature': 22, 'hvac_mode': 'heat'}"
                        ),
                    },
                },
                "required": ["domain", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_automation",
            "description": (
                "Erstellt eine neue Home Assistant Automation. "
                "Verwende echte HA-Automation-YAML-Syntax für trigger/condition/action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "description": "Name der Automation"},
                    "description": {"type": "string", "description": "Optionale Beschreibung"},
                    "trigger": {
                        "type": "array",
                        "description": "Liste von Auslösern (HA trigger-Syntax)",
                        "items": {"type": "object"},
                    },
                    "condition": {
                        "type": "array",
                        "description": "Optionale Bedingungsliste",
                        "items": {"type": "object"},
                    },
                    "action": {
                        "type": "array",
                        "description": "Liste von Aktionen",
                        "items": {"type": "object"},
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["single", "parallel", "queued", "restart"],
                        "description": "Ausführungsmodus (Standard: single)",
                    },
                },
                "required": ["alias", "trigger", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_scene",
            "description": (
                "Erstellt eine neue Szene mit festgelegten Entity-Zuständen. "
                "Nützlich um Stimmungen wie 'Filmabend' oder 'Guten Morgen' zu speichern."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name der Szene"},
                    "entities": {
                        "type": "object",
                        "description": (
                            "entity_id → Zustand. Beispiel: "
                            "{'light.wohnzimmer': {'state': 'on', 'brightness': 100, 'color_temp': 3000}}"
                        ),
                    },
                },
                "required": ["name", "entities"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_entity",
            "description": "Benennt eine Entity um (ändert den friendly_name dauerhaft).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Die Entity-ID"},
                    "new_name": {"type": "string", "description": "Der neue Anzeigename"},
                },
                "required": ["entity_id", "new_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_area",
            "description": "Weist eine Entity einem Bereich (Raum) zu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Die Entity-ID"},
                    "area_id": {
                        "type": "string",
                        "description": "Die Bereich-ID aus der Bereiche-Liste",
                    },
                },
                "required": ["entity_id", "area_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_details",
            "description": (
                "Gibt vollständige Informationen über eine einzelne Entity zurück "
                "(alle Attribute, letzter Zustand, Zeitstempel)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Die Entity-ID"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_history",
            "description": "Gibt den Zustandsverlauf einer Entity für einen bestimmten Zeitraum zurück.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Die Entity-ID"},
                    "hours": {
                        "type": "number",
                        "description": "Stunden zurück (Standard: 24, max: 168)",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_dashboard",
            "description": (
                "Generiert ein neues AI-Dashboard auf Basis aller aktuellen Entities "
                "und wendet es optional direkt an."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "auto_apply": {
                        "type": "boolean",
                        "description": "Dashboard direkt anwenden (Standard: false)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_entities",
            "description": (
                "Sucht Entities nach Domain, Bereich, Geräteklasse oder Namensfragment. "
                "Nützlich wenn du nicht die genaue entity_id kennst."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Filtern nach Domain (z.B. 'light', 'sensor')",
                    },
                    "area": {
                        "type": "string",
                        "description": "Filtern nach Bereichsname (z.B. 'Wohnzimmer')",
                    },
                    "device_class": {
                        "type": "string",
                        "description": "Filtern nach Geräteklasse (z.B. 'temperature', 'motion')",
                    },
                    "name_contains": {
                        "type": "string",
                        "description": "Namensteilstring (case-insensitive Suche)",
                    },
                    "state": {
                        "type": "string",
                        "description": "Nur Entities mit diesem Zustand zurückgeben (z.B. 'on', 'off')",
                    },
                },
                "required": [],
            },
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Format converters
# ─────────────────────────────────────────────────────────────────────────────

def get_anthropic_tools() -> list[dict]:
    """Convert to Anthropic tool-use format."""
    result = []
    for tool in TOOL_DEFINITIONS:
        fn = tool["function"]
        result.append(
            {
                "name": fn["name"],
                "description": fn["description"],
                "input_schema": fn["parameters"],
            }
        )
    return result


def get_google_tools() -> list[dict]:
    """Convert to Google Gemini functionDeclarations format."""
    result = []
    for tool in TOOL_DEFINITIONS:
        fn = tool["function"]
        result.append(
            {
                "name": fn["name"],
                "description": fn["description"],
                "parameters": fn["parameters"],
            }
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Tool executor
# ─────────────────────────────────────────────────────────────────────────────

class HAToolExecutor:
    """Executes AI tool calls against Home Assistant."""

    # Tools that actually mutate HA state
    DESTRUCTIVE_TOOLS = frozenset(
        {
            "call_service",
            "create_automation",
            "create_scene",
            "rename_entity",
            "assign_area",
            "generate_dashboard",
        }
    )

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def is_destructive(self, tool_name: str) -> bool:
        return tool_name in self.DESTRUCTIVE_TOOLS

    async def async_execute(self, tool_name: str, tool_args: dict) -> dict:
        """Dispatch a tool call and return the result."""
        _LOGGER.info("AI tool call: %s  args=%s", tool_name, tool_args)
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return {"error": f"Unbekanntes Tool: {tool_name}"}
            return await handler(tool_args)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Tool '%s' failed: %s", tool_name, err)
            return {"error": str(err)}

    # ── Individual tool handlers ──────────────────────────────────

    async def _tool_call_service(self, args: dict) -> dict:
        domain = args["domain"]
        service = args["service"]
        service_data: dict[str, Any] = dict(args.get("service_data") or {})
        entity_id = args.get("entity_id")
        if entity_id:
            service_data["entity_id"] = entity_id
        await self.hass.services.async_call(domain, service, service_data, blocking=True)
        return {
            "success": True,
            "message": f"Service {domain}.{service} ausgeführt"
            + (f" für {entity_id}" if entity_id else ""),
        }

    async def _tool_create_automation(self, args: dict) -> dict:
        config: dict[str, Any] = {
            "alias": args["alias"],
            "description": args.get("description", ""),
            "trigger": args["trigger"],
            "action": args["action"],
            "mode": args.get("mode", "single"),
        }
        if args.get("condition"):
            config["condition"] = args["condition"]
        await self.hass.services.async_call(
            "automation",
            "create",
            {"config": config},
            blocking=True,
        )
        return {"success": True, "message": f"Automation '{args['alias']}' erstellt."}

    async def _tool_create_scene(self, args: dict) -> dict:
        scene_id = args["name"].lower().replace(" ", "_").replace("-", "_")
        await self.hass.services.async_call(
            "scene",
            "create",
            {"scene_id": scene_id, "entities": args["entities"]},
            blocking=True,
        )
        return {"success": True, "message": f"Szene '{args['name']}' erstellt."}

    async def _tool_rename_entity(self, args: dict) -> dict:
        entity_reg = er.async_get(self.hass)
        entry = entity_reg.async_get(args["entity_id"])
        if not entry:
            return {"error": f"Entity nicht gefunden: {args['entity_id']}"}
        entity_reg.async_update_entity(args["entity_id"], name=args["new_name"])
        return {
            "success": True,
            "message": f"'{args['entity_id']}' umbenannt in '{args['new_name']}'.",
        }

    async def _tool_assign_area(self, args: dict) -> dict:
        entity_reg = er.async_get(self.hass)
        entry = entity_reg.async_get(args["entity_id"])
        if not entry:
            return {"error": f"Entity nicht gefunden: {args['entity_id']}"}
        # Validate area
        area_reg = ar.async_get(self.hass)
        area = area_reg.async_get_area(args["area_id"])
        if not area:
            return {"error": f"Bereich nicht gefunden: {args['area_id']}"}
        entity_reg.async_update_entity(args["entity_id"], area_id=args["area_id"])
        return {
            "success": True,
            "message": f"'{args['entity_id']}' dem Bereich '{area.name}' zugewiesen.",
        }

    async def _tool_get_entity_details(self, args: dict) -> dict:
        entity_id = args["entity_id"]
        state = self.hass.states.get(entity_id)
        if state is None:
            return {"error": f"Entity nicht gefunden: {entity_id}"}

        entity_reg = er.async_get(self.hass)
        entry = entity_reg.async_get(entity_id)

        area_name: str | None = None
        if entry and entry.area_id:
            area_reg = ar.async_get(self.hass)
            area_obj = area_reg.async_get_area(entry.area_id)
            area_name = area_obj.name if area_obj else None

        return {
            "entity_id": entity_id,
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat(),
            "last_updated": state.last_updated.isoformat(),
            "area": area_name,
            "device_class": state.attributes.get("device_class"),
            "unit": state.attributes.get("unit_of_measurement"),
        }

    async def _tool_get_entity_history(self, args: dict) -> dict:
        import datetime

        entity_id = args["entity_id"]
        hours = min(int(args.get("hours", 24)), 168)

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import (
                get_significant_states,
            )

            start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
                hours=hours
            )
            instance = get_instance(self.hass)
            history = await instance.async_add_executor_job(
                get_significant_states,
                self.hass,
                start,
                None,
                [entity_id],
            )
            states = history.get(entity_id, [])
            return {
                "entity_id": entity_id,
                "hours_requested": hours,
                "count": len(states),
                "history": [
                    {
                        "state": s.state,
                        "last_changed": s.last_changed.isoformat(),
                        "unit": s.attributes.get("unit_of_measurement"),
                    }
                    for s in states[-50:]
                ],
            }
        except Exception as err:  # pylint: disable=broad-except
            return {"error": f"Verlauf nicht verfügbar: {err}"}

    async def _tool_generate_dashboard(self, args: dict) -> dict:
        from .const import DOMAIN

        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return {"error": "AI Dashboard Integration nicht eingerichtet."}
        entry = entries[0]
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if entry_data is None:
            return {"error": "Keine Integrationsdaten gefunden."}

        from .dashboard_generator import DashboardGenerator
        from .entity_analyzer import EntityAnalyzer

        entry_data["status"] = "generating"
        try:
            analyzer = EntityAnalyzer(self.hass)
            areas_data = await analyzer.async_get_areas_with_entities()
            generator = DashboardGenerator(self.hass, entry.data, entry.options)
            config = await generator.async_generate(
                areas_data, images=entry_data.get("images", {})
            )
            import datetime

            entry_data["last_config"] = config
            entry_data["last_generated"] = datetime.datetime.now().isoformat()
            entry_data["status"] = "done"

            await entry_data["store"].async_save(
                {
                    "last_generated": entry_data["last_generated"],
                    "last_config": config,
                }
            )

            if args.get("auto_apply", False):
                await generator.async_apply_dashboard(config)
                return {"success": True, "message": "Dashboard generiert und angewendet."}

            return {"success": True, "message": "Dashboard generiert. Klicke auf 'Anwenden' im Dashboard-Tab."}
        except Exception as err:  # pylint: disable=broad-except
            entry_data["status"] = "error"
            return {"error": f"Dashboard-Generierung fehlgeschlagen: {err}"}

    async def _tool_find_entities(self, args: dict) -> dict:
        domain_filter = args.get("domain", "").lower()
        area_filter = args.get("area", "").lower()
        dc_filter = args.get("device_class", "").lower()
        name_filter = args.get("name_contains", "").lower()
        state_filter = args.get("state", "").lower()

        from homeassistant.helpers import area_registry as ar
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        area_reg = ar.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)

        device_area_map: dict[str, str] = {
            d.id: d.area_id for d in device_reg.devices.values() if d.area_id
        }

        results = []
        for entry in entity_reg.entities.values():
            state = self.hass.states.get(entry.entity_id)
            if state is None:
                continue

            eid = entry.entity_id
            dom = eid.split(".")[0]

            if domain_filter and dom != domain_filter:
                continue

            if state_filter and state.state.lower() != state_filter:
                continue

            dc = (state.attributes.get("device_class") or entry.device_class or "").lower()
            if dc_filter and dc_filter not in dc:
                continue

            area_id = entry.area_id or device_area_map.get(entry.device_id or "")
            area_name = ""
            if area_id:
                a = area_reg.async_get_area(area_id)
                area_name = a.name if a else ""

            if area_filter and area_filter not in area_name.lower():
                continue

            fname = state.attributes.get("friendly_name", eid)
            if name_filter and name_filter not in fname.lower() and name_filter not in eid.lower():
                continue

            unit = state.attributes.get("unit_of_measurement", "")
            results.append(
                {
                    "entity_id": eid,
                    "name": fname,
                    "domain": dom,
                    "state": state.state + (f" {unit}" if unit else ""),
                    "area": area_name,
                    "device_class": dc or None,
                }
            )

        return {
            "count": len(results),
            "entities": results[:50],  # cap to avoid huge responses
        }
