"""AI Dashboard Generator - Main integration setup."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.typing import ConfigType

from .const import (  # noqa: E402
    CONF_BASE_URL,
    DOMAIN,
    PLATFORMS,
    PANEL_COMPONENT_NAME,
    PANEL_SIDEBAR_TITLE,
    PANEL_SIDEBAR_ICON,
    PANEL_URL,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORAGE_KEY_IMAGES,
    STATUS_IDLE,
    STATUS_GENERATING,
    STATUS_DONE,
    STATUS_ERROR,
    WS_COMMAND_GET_AREAS,
    WS_COMMAND_GET_STATUS,
    WS_COMMAND_GENERATE,
    WS_COMMAND_APPLY,
    WS_COMMAND_GET_PREVIEW,
    WS_COMMAND_UPLOAD_IMAGE,
    WS_COMMAND_DELETE_IMAGE,
    WS_COMMAND_GET_IMAGES,
    WS_COMMAND_UPDATE_SETTINGS,
    WS_COMMAND_GET_SETTINGS,
    WS_COMMAND_ASSISTANT_CHAT,
    WS_COMMAND_ASSISTANT_EXECUTE,
    WS_COMMAND_ASSISTANT_CLEAR,
    WS_COMMAND_ASSISTANT_HISTORY,
    SERVICE_GENERATE_DASHBOARD,
    SERVICE_REFRESH_DASHBOARD,
    HTTP_IMAGE_UPLOAD,
    HTTP_IMAGE_SERVE,
)

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the AI Dashboard component."""
    hass.data.setdefault(DOMAIN, {})
    return True


def _get_entry_value(entry: ConfigEntry, key: str, default: Any = "") -> Any:
    """Read a setting from options first, then data, then return default."""
    val = entry.options.get(key)
    if val is not None and val != "":
        return val
    return entry.data.get(key, default)


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when options are saved – reset assistant so new settings are picked up."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is not None:
        entry_data.pop("assistant", None)
    _LOGGER.debug("AI Dashboard options updated – assistant session reset")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AI Dashboard from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize storage
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    image_store = Store(hass, STORAGE_VERSION, STORAGE_KEY_IMAGES)

    stored_data = await store.async_load() or {}
    stored_images = await image_store.async_load() or {}

    hass.data[DOMAIN][entry.entry_id] = {
        "config_entry": entry,
        "store": store,
        "image_store": image_store,
        "status": STATUS_IDLE,
        "last_generated": stored_data.get("last_generated"),
        "last_config": stored_data.get("last_config"),
        "images": stored_images,
        "generation_task": None,
        "error_message": None,
    }

    # Copy frontend files to www directory
    await _async_copy_frontend_files(hass)

    # Register the frontend panel
    await _async_register_panel(hass, entry)

    # Register WebSocket API handlers (guard: only once per hass instance)
    if not hass.data[DOMAIN].get("_ws_registered"):
        _register_websocket_handlers(hass)
        hass.data[DOMAIN]["_ws_registered"] = True

    # Register HTTP endpoints
    await _async_register_http_endpoints(hass, entry)

    # Register services
    _register_services(hass, entry)

    # Listen for options changes
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info("AI Dashboard Generator setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove panel
    try:
        frontend.async_remove_panel(hass, PANEL_URL)
    except Exception:  # pylint: disable=broad-except
        pass

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def _async_copy_frontend_files(hass: HomeAssistant) -> None:
    """Copy (always overwrite) frontend JS files to the www directory."""
    www_dir = Path(hass.config.path("www")) / "ai_dashboard"
    www_dir.mkdir(parents=True, exist_ok=True)

    frontend_dir = Path(__file__).parent / "frontend"

    def _copy_files():
        for src_file in frontend_dir.glob("*.js"):
            dst_file = www_dir / src_file.name
            # Always overwrite so updated versions are deployed immediately
            shutil.copy2(src_file, dst_file)
        _LOGGER.debug("Frontend files copied to %s", www_dir)

    await hass.async_add_executor_job(_copy_files)


async def _async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the configuration panel in HA sidebar."""
    from .const import VERSION as INTEGRATION_VERSION
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_SIDEBAR_TITLE,
        sidebar_icon=PANEL_SIDEBAR_ICON,
        frontend_url_path=PANEL_URL,
        config={
            "_panel_custom": {
                "name": PANEL_COMPONENT_NAME,
                # Use the full integration version string for proper cache-busting
                "js_url": f"/local/ai_dashboard/ai-dashboard-panel.js?v={INTEGRATION_VERSION}",
                "embed_iframe": False,
                "trust_external": False,
            }
        },
        require_admin=False,
    )


def _register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register WebSocket API handlers."""

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_GET_AREAS})
    @websocket_api.async_response
    async def ws_get_areas(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Handle get areas WebSocket command."""
        from .entity_analyzer import EntityAnalyzer

        try:
            analyzer = EntityAnalyzer(hass)
            areas_data = await analyzer.async_get_areas_with_entities()
            connection.send_result(msg["id"], {"areas": areas_data})
        except Exception as err:  # pylint: disable=broad-except
            connection.send_error(msg["id"], "get_areas_failed", str(err))

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_GET_STATUS})
    @websocket_api.async_response
    async def ws_get_status(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Handle get status WebSocket command."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        connection.send_result(
            msg["id"],
            {
                "status": entry_data["status"],
                "last_generated": entry_data["last_generated"],
                "error_message": entry_data.get("error_message"),
                "has_dashboard": entry_data["last_config"] is not None,
            },
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_COMMAND_GENERATE,
            vol.Optional("options", default={}): dict,
        }
    )
    @websocket_api.async_response
    async def ws_generate(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Handle dashboard generation WebSocket command."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        if entry_data["status"] == STATUS_GENERATING:
            connection.send_error(
                msg["id"], "already_generating", "Dashboard generation already in progress"
            )
            return

        # Get first config entry
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No config entry found")
            return

        entry = entries[0]

        async def _do_generate():
            from .dashboard_generator import DashboardGenerator
            from .entity_analyzer import EntityAnalyzer

            entry_data["status"] = STATUS_GENERATING
            entry_data["error_message"] = None

            try:
                analyzer = EntityAnalyzer(hass)
                areas_data = await analyzer.async_get_areas_with_entities()

                generator = DashboardGenerator(hass, entry.data, entry.options)
                config = await generator.async_generate(
                    areas_data,
                    images=entry_data.get("images", {}),
                    options=msg.get("options", {}),
                )

                import datetime
                entry_data["last_config"] = config
                entry_data["last_generated"] = datetime.datetime.now().isoformat()
                entry_data["status"] = STATUS_DONE

                # Persist
                await entry_data["store"].async_save(
                    {
                        "last_generated": entry_data["last_generated"],
                        "last_config": config,
                    }
                )

                # Fire event
                hass.bus.async_fire(
                    f"{DOMAIN}_generated",
                    {"status": "success"},
                )

            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Error generating dashboard: %s", err)
                entry_data["status"] = STATUS_ERROR
                entry_data["error_message"] = str(err)
                hass.bus.async_fire(
                    f"{DOMAIN}_generated",
                    {"status": "error", "error": str(err)},
                )

        asyncio.ensure_future(_do_generate())
        connection.send_result(msg["id"], {"started": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_APPLY})
    @websocket_api.async_response
    async def ws_apply(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Apply the generated dashboard to HA."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None or entry_data.get("last_config") is None:
            connection.send_error(
                msg["id"], "no_config", "No generated dashboard available. Generate first."
            )
            return

        try:
            from .dashboard_generator import DashboardGenerator
            entries = hass.config_entries.async_entries(DOMAIN)
            entry = entries[0]
            generator = DashboardGenerator(hass, entry.data, entry.options)
            await generator.async_apply_dashboard(entry_data["last_config"])
            connection.send_result(msg["id"], {"applied": True})
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error applying dashboard: %s", err)
            connection.send_error(msg["id"], "apply_failed", str(err))

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_GET_PREVIEW})
    @websocket_api.async_response
    async def ws_get_preview(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return the last generated dashboard config."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        connection.send_result(
            msg["id"],
            {"config": entry_data.get("last_config")},
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_COMMAND_UPLOAD_IMAGE,
            vol.Required("area_id"): str,
            vol.Required("image_data"): str,  # base64 encoded
            vol.Required("filename"): str,
        }
    )
    @websocket_api.async_response
    async def ws_upload_image(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Handle image upload for a room."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        import base64

        try:
            area_id = msg["area_id"]
            image_data = base64.b64decode(msg["image_data"])
            filename = msg["filename"]

            # Validate image size (max 5MB)
            if len(image_data) > 5 * 1024 * 1024:
                connection.send_error(
                    msg["id"], "image_too_large", "Image must be smaller than 5MB"
                )
                return

            # Save image to www directory
            images_dir = Path(hass.config.path("www")) / "ai_dashboard" / "room_images"
            images_dir.mkdir(parents=True, exist_ok=True)

            safe_name = f"{area_id}_{filename.replace(' ', '_')}"
            # Only allow safe extensions
            ext = Path(filename).suffix.lower()
            if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                connection.send_error(
                    msg["id"], "invalid_format", "Only JPG, PNG, WEBP supported"
                )
                return

            safe_name = f"{area_id}{ext}"
            image_path = images_dir / safe_name

            def _write_image():
                with open(image_path, "wb") as f:
                    f.write(image_data)

            await hass.async_add_executor_job(_write_image)

            image_url = f"/local/ai_dashboard/room_images/{safe_name}"

            # Store reference
            entry_data["images"][area_id] = image_url
            await entry_data["image_store"].async_save(entry_data["images"])

            connection.send_result(
                msg["id"], {"success": True, "url": image_url}
            )

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error uploading image: %s", err)
            connection.send_error(msg["id"], "upload_failed", str(err))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_COMMAND_DELETE_IMAGE,
            vol.Required("area_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_delete_image(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Delete a room image."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        area_id = msg["area_id"]
        if area_id in entry_data["images"]:
            # Try to delete file
            image_url = entry_data["images"][area_id]
            local_path = image_url.replace(
                "/local/", hass.config.path("www") + "/"
            )
            try:
                await hass.async_add_executor_job(os.remove, local_path)
            except OSError:
                pass
            del entry_data["images"][area_id]
            await entry_data["image_store"].async_save(entry_data["images"])

        connection.send_result(msg["id"], {"deleted": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_GET_IMAGES})
    @websocket_api.async_response
    async def ws_get_images(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return all room images."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        connection.send_result(msg["id"], {"images": entry_data.get("images", {})})

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_COMMAND_UPDATE_SETTINGS,
            vol.Required("settings"): dict,
        }
    )
    @websocket_api.async_response
    async def ws_update_settings(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Update integration settings."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        entry = entries[0]
        new_options = {**entry.options, **msg["settings"]}
        hass.config_entries.async_update_entry(entry, options=new_options)
        connection.send_result(msg["id"], {"updated": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_GET_SETTINGS})
    @websocket_api.async_response
    async def ws_get_settings(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return current settings."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        entry = entries[0]
        connection.send_result(
            msg["id"],
            {
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
        )

    # ── AI Assistant WebSocket commands ──────────────────────────

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_COMMAND_ASSISTANT_CHAT,
            vol.Required("message"): str,
            vol.Optional("auto_execute", default=False): bool,
            vol.Optional("context_depth", default="standard"): str,
        }
    )
    @websocket_api.async_response
    async def ws_assistant_chat(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Send a message to the AI assistant."""
        from .ai_assistant import AIAssistant

        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        entry = entries[0]
        provider = _get_entry_value(entry, "ai_provider", "groq")
        api_key = _get_entry_value(entry, "api_key", "")
        model = _get_entry_value(entry, "ai_model", "")
        base_url = _get_entry_value(entry, "base_url", "")
        language = entry.options.get("language") or entry.data.get("language", "de")

        # Retrieve or create a persistent assistant per config entry
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        assistant: AIAssistant | None = entry_data.get("assistant")
        if assistant is None:
            assistant = AIAssistant(hass, provider, api_key, model, base_url, language)
            entry_data["assistant"] = assistant

        # Sync provider settings in case they changed
        assistant.provider = provider
        assistant.api_key = api_key
        assistant.model = model
        assistant.base_url = base_url
        assistant.language = language

        try:
            result = await assistant.async_chat(
                msg["message"],
                auto_execute=msg.get("auto_execute", False),
                context_depth=msg.get("context_depth", "standard"),
            )
            connection.send_result(msg["id"], result)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Assistant chat failed: %s", err)
            connection.send_error(msg["id"], "assistant_error", str(err))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_COMMAND_ASSISTANT_EXECUTE,
            vol.Required("actions"): list,
        }
    )
    @websocket_api.async_response
    async def ws_assistant_execute(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Execute confirmed pending actions."""
        from .ai_assistant import AIAssistant

        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_setup", "Integration not set up")
            return

        entry = entries[0]
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        assistant: AIAssistant | None = entry_data.get("assistant")
        if assistant is None:
            connection.send_error(msg["id"], "no_session", "No active assistant session")
            return

        try:
            results = await assistant.async_execute_confirmed_actions(msg["actions"])
            connection.send_result(msg["id"], {"results": results})
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Assistant execute failed: %s", err)
            connection.send_error(msg["id"], "execute_error", str(err))

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_ASSISTANT_CLEAR})
    @websocket_api.async_response
    async def ws_assistant_clear(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Clear the assistant conversation history."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry_data = hass.data[DOMAIN].get(entries[0].entry_id, {})
            assistant = entry_data.get("assistant")
            if assistant:
                assistant.clear_history()
        connection.send_result(msg["id"], {"cleared": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_COMMAND_ASSISTANT_HISTORY})
    @websocket_api.async_response
    async def ws_assistant_history(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Return the assistant conversation history."""
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_result(msg["id"], {"history": []})
            return
        entry_data = hass.data[DOMAIN].get(entries[0].entry_id, {})
        assistant = entry_data.get("assistant")
        history = assistant.get_history() if assistant else []
        connection.send_result(msg["id"], {"history": history})

    # Register all handlers
    websocket_api.async_register_command(hass, ws_get_areas)
    websocket_api.async_register_command(hass, ws_get_status)
    websocket_api.async_register_command(hass, ws_generate)
    websocket_api.async_register_command(hass, ws_apply)
    websocket_api.async_register_command(hass, ws_get_preview)
    websocket_api.async_register_command(hass, ws_upload_image)
    websocket_api.async_register_command(hass, ws_delete_image)
    websocket_api.async_register_command(hass, ws_get_images)
    websocket_api.async_register_command(hass, ws_update_settings)
    websocket_api.async_register_command(hass, ws_get_settings)
    websocket_api.async_register_command(hass, ws_assistant_chat)
    websocket_api.async_register_command(hass, ws_assistant_execute)
    websocket_api.async_register_command(hass, ws_assistant_clear)
    websocket_api.async_register_command(hass, ws_assistant_history)


async def _async_register_http_endpoints(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Register HTTP API endpoints."""
    # HTTP endpoints are handled via WebSocket for now
    pass


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register HA services."""

    async def async_generate_dashboard(call: ServiceCall) -> None:
        """Service to generate a new AI dashboard."""
        entry_data = _get_first_entry_data(hass)
        if entry_data is None:
            raise HomeAssistantError("AI Dashboard integration not set up")

        from .dashboard_generator import DashboardGenerator
        from .entity_analyzer import EntityAnalyzer

        entry_data["status"] = STATUS_GENERATING
        entry_data["error_message"] = None

        try:
            entries = hass.config_entries.async_entries(DOMAIN)
            if not entries:
                raise HomeAssistantError("No config entry found")
            cfg_entry = entries[0]

            analyzer = EntityAnalyzer(hass)
            areas_data = await analyzer.async_get_areas_with_entities()

            generator = DashboardGenerator(hass, cfg_entry.data, cfg_entry.options)
            config = await generator.async_generate(
                areas_data, images=entry_data.get("images", {})
            )

            import datetime
            entry_data["last_config"] = config
            entry_data["last_generated"] = datetime.datetime.now().isoformat()
            entry_data["status"] = STATUS_DONE

            await entry_data["store"].async_save(
                {
                    "last_generated": entry_data["last_generated"],
                    "last_config": config,
                }
            )

            # Auto-apply if requested
            if call.data.get("auto_apply", True):
                await generator.async_apply_dashboard(config)

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Service generate_dashboard failed: %s", err)
            entry_data["status"] = STATUS_ERROR
            entry_data["error_message"] = str(err)
            raise HomeAssistantError(f"Dashboard generation failed: {err}") from err

    async def async_refresh_dashboard(call: ServiceCall) -> None:
        """Service alias for refresh (same as generate)."""
        await async_generate_dashboard(call)

    hass.services.async_register(DOMAIN, SERVICE_GENERATE_DASHBOARD, async_generate_dashboard)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH_DASHBOARD, async_refresh_dashboard)


def _get_first_entry_data(hass: HomeAssistant) -> dict | None:
    """Get data for the first config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    return hass.data.get(DOMAIN, {}).get(entries[0].entry_id)
