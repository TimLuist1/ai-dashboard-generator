"""Config flow for AI Dashboard Generator."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_AI_PROVIDER,
    CONF_AI_MODEL,
    CONF_API_KEY,
    CONF_DASHBOARD_TITLE,
    CONF_DASHBOARD_URL_PATH,
    CONF_USE_MUSHROOM,
    CONF_LANGUAGE,
    CONF_BASE_URL,
    AI_PROVIDER_OPENAI,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_GOOGLE,
    AI_PROVIDER_GROQ,
    AI_PROVIDER_OPENCODE,
    OPENCODE_DEFAULT_BASE_URL,
    AI_PROVIDERS,
    AI_MODELS,
    DEFAULT_DASHBOARD_TITLE,
    DEFAULT_DASHBOARD_URL_PATH,
    DEFAULT_AI_PROVIDER,
)

_LOGGER = logging.getLogger(__name__)

_DOCS_URL = "https://github.com/TimLuist1/ai-dashboard-generator"
_PROVIDER_NAMES = {
    AI_PROVIDER_OPENAI: "OpenAI",
    AI_PROVIDER_ANTHROPIC: "Anthropic",
    AI_PROVIDER_GOOGLE: "Google",
    AI_PROVIDER_GROQ: "Groq",
    AI_PROVIDER_OPENCODE: "OpenCode.ai",
}


def _model_choices(provider: str) -> dict[str, str]:
    """Return model id → label mapping for a given provider."""
    return {mid: mname for mid, mname in AI_MODELS.get(provider, [])}


def _default_model(provider: str) -> str:
    """Return the first model id for a provider, or empty string."""
    choices = _model_choices(provider)
    return next(iter(choices), "")


class AIDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for AI Dashboard Generator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step – basic configuration."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_api_key()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DASHBOARD_TITLE, default=DEFAULT_DASHBOARD_TITLE
                ): str,
                vol.Required(
                    CONF_AI_PROVIDER, default=DEFAULT_AI_PROVIDER
                ): vol.In(AI_PROVIDERS),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"docs_url": _DOCS_URL},
        )

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step for entering the API key."""
        errors: dict[str, str] = {}
        provider = self._data.get(CONF_AI_PROVIDER, AI_PROVIDER_GROQ)
        model_choices = _model_choices(provider)
        default_model = _default_model(provider)
        is_opencode = provider == AI_PROVIDER_OPENCODE

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            model = user_input.get(CONF_AI_MODEL, default_model)
            base_url = user_input.get(CONF_BASE_URL, OPENCODE_DEFAULT_BASE_URL).strip()

            if api_key:
                validate_base_url = base_url if is_opencode else ""
                valid = await _async_validate_api_key(self.hass, provider, api_key, model, validate_base_url)
                if not valid:
                    errors["base"] = "invalid_api_key"

            if not errors:
                entry_data = {
                    **self._data,
                    CONF_API_KEY: api_key,
                    CONF_AI_MODEL: model,
                    CONF_DASHBOARD_URL_PATH: DEFAULT_DASHBOARD_URL_PATH,
                }
                if is_opencode:
                    entry_data[CONF_BASE_URL] = base_url or OPENCODE_DEFAULT_BASE_URL
                return self.async_create_entry(
                    title=self._data.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE),
                    data=entry_data,
                    options={
                        CONF_USE_MUSHROOM: True,
                        CONF_LANGUAGE: "de",
                    },
                )

        schema_fields = {
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_AI_MODEL, default=default_model): vol.In(model_choices),
        }
        if is_opencode:
            schema_fields[vol.Optional(CONF_BASE_URL, default=OPENCODE_DEFAULT_BASE_URL)] = str

        schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="api_key",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "provider": _PROVIDER_NAMES.get(provider, provider),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AIDashboardOptionsFlow:
        """Return the options flow handler."""
        return AIDashboardOptionsFlow()


class AIDashboardOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for AI Dashboard.

    NOTE: Do NOT override __init__ with config_entry – it is set automatically
    by HA 2024.3+ via self.config_entry.
    """

    def __init__(self) -> None:
        """Initialize options flow."""
        self._new_provider: str = ""
        self._base_input: dict[str, Any] = {}

    # ------------------------------------------------------------------ step 1
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options – provider / title / UI settings."""
        entry = self.config_entry
        errors: dict[str, str] = {}

        current_provider = (
            entry.options.get(CONF_AI_PROVIDER)
            or entry.data.get(CONF_AI_PROVIDER, DEFAULT_AI_PROVIDER)
        )
        current_title = (
            entry.options.get(CONF_DASHBOARD_TITLE)
            or entry.data.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE)
        )

        if user_input is not None:
            new_provider = user_input.get(CONF_AI_PROVIDER, DEFAULT_AI_PROVIDER)
            self._new_provider = new_provider
            self._base_input = user_input
            return await self.async_step_model()

        schema = vol.Schema(
            {
                vol.Required(CONF_AI_PROVIDER, default=current_provider): vol.In(AI_PROVIDERS),
                vol.Optional(CONF_DASHBOARD_TITLE, default=current_title): str,
                vol.Required(
                    CONF_USE_MUSHROOM,
                    default=entry.options.get(CONF_USE_MUSHROOM, True),
                ): bool,
                vol.Required(
                    CONF_LANGUAGE,
                    default=entry.options.get(CONF_LANGUAGE, "de"),
                ): vol.In({"de": "Deutsch", "en": "English"}),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------ step 2
    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """API key + model selection for the chosen provider."""
        errors: dict[str, str] = {}
        entry = self.config_entry
        provider = self._new_provider or entry.data.get(CONF_AI_PROVIDER, DEFAULT_AI_PROVIDER)

        model_choices = _model_choices(provider)
        current_model = (
            entry.options.get(CONF_AI_MODEL)
            or entry.data.get(CONF_AI_MODEL, "")
        )
        default_model = current_model if current_model in model_choices else _default_model(provider)
        current_key = (
            entry.options.get(CONF_API_KEY)
            or entry.data.get(CONF_API_KEY, "")
        )

        if user_input is not None:
            raw_key = user_input.get(CONF_API_KEY, "").strip()
            api_key = raw_key if raw_key else current_key
            model = user_input.get(CONF_AI_MODEL, default_model)

            if api_key:
                valid = await _async_validate_api_key(self.hass, provider, api_key, model)
                if not valid:
                    errors["base"] = "invalid_api_key"
            else:
                errors["base"] = "invalid_api_key"

            if not errors:
                new_title = self._base_input.get(
                    CONF_DASHBOARD_TITLE
                ) or entry.data.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE)
                new_options = {
                    **entry.options,
                    CONF_AI_PROVIDER: provider,
                    CONF_API_KEY: api_key,
                    CONF_AI_MODEL: model,
                    CONF_DASHBOARD_TITLE: new_title,
                    CONF_USE_MUSHROOM: self._base_input.get(
                        CONF_USE_MUSHROOM, entry.options.get(CONF_USE_MUSHROOM, True)
                    ),
                    CONF_LANGUAGE: self._base_input.get(
                        CONF_LANGUAGE, entry.options.get(CONF_LANGUAGE, "de")
                    ),
                }
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_AI_PROVIDER: provider,
                        CONF_API_KEY: api_key,
                        CONF_AI_MODEL: model,
                        CONF_DASHBOARD_TITLE: new_title,
                    },
                )
                return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Required(CONF_AI_MODEL, default=default_model): vol.In(model_choices),
            }
        )

        return self.async_show_form(
            step_id="model",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "provider": _PROVIDER_NAMES.get(provider, provider),
                "current_key_hint": "✓ gespeichert" if current_key else "—",
            },
        )


async def _async_validate_api_key(hass: Any, provider: str, api_key: str, model: str, base_url: str = "") -> bool:
    """Validate the API key with a lightweight test request."""
    if not api_key:
        return False
    try:
        from .ai_provider import create_ai_provider
        ai = create_ai_provider(hass, provider, api_key, model, base_url)
        return await ai.async_test_connection()
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("API key validation failed: %s", err)
        return False
