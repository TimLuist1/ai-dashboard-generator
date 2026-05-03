"""Config flow for AI Dashboard Generator."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_AI_PROVIDER,
    CONF_AI_MODEL,
    CONF_API_KEY,
    CONF_DASHBOARD_TITLE,
    CONF_DASHBOARD_URL_PATH,
    CONF_USE_MUSHROOM,
    CONF_LANGUAGE,
    AI_PROVIDER_OFFLINE,
    AI_PROVIDER_OPENAI,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_GOOGLE,
    AI_PROVIDERS,
    DEFAULT_DASHBOARD_TITLE,
    DEFAULT_DASHBOARD_URL_PATH,
    DEFAULT_AI_PROVIDER,
)

_LOGGER = logging.getLogger(__name__)


class AIDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for AI Dashboard Generator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - basic configuration."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            provider = user_input.get(CONF_AI_PROVIDER, AI_PROVIDER_OFFLINE)

            if provider != AI_PROVIDER_OFFLINE:
                return await self.async_step_api_key()

            return self.async_create_entry(
                title=user_input.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE),
                data={
                    CONF_AI_PROVIDER: provider,
                    CONF_AI_MODEL: "",
                    CONF_API_KEY: "",
                    CONF_DASHBOARD_TITLE: user_input.get(
                        CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE
                    ),
                    CONF_DASHBOARD_URL_PATH: DEFAULT_DASHBOARD_URL_PATH,
                },
                options={
                    CONF_USE_MUSHROOM: True,
                    CONF_LANGUAGE: "de",
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DASHBOARD_TITLE, default=DEFAULT_DASHBOARD_TITLE
                ): str,
                vol.Required(
                    CONF_AI_PROVIDER, default=AI_PROVIDER_OFFLINE
                ): vol.In(AI_PROVIDERS),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/YOUR_USERNAME/ai-dashboard-generator"
            },
        )

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step for entering the API key."""
        errors: dict[str, str] = {}
        provider = self._data.get(CONF_AI_PROVIDER, AI_PROVIDER_OFFLINE)

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            model = user_input.get(CONF_AI_MODEL, "")

            # Validate API key by testing a simple request
            valid = await self._async_validate_api_key(provider, api_key, model)
            if not valid:
                errors["base"] = "invalid_api_key"
            else:
                return self.async_create_entry(
                    title=self._data.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE),
                    data={
                        **self._data,
                        CONF_API_KEY: api_key,
                        CONF_AI_MODEL: model,
                        CONF_DASHBOARD_URL_PATH: DEFAULT_DASHBOARD_URL_PATH,
                    },
                    options={
                        CONF_USE_MUSHROOM: True,
                        CONF_LANGUAGE: "de",
                    },
                )

        # Build model choices based on provider
        from .const import AI_MODELS

        model_choices = {}
        if provider in AI_MODELS:
            for model_id, model_name in AI_MODELS[provider]:
                model_choices[model_id] = model_name
        default_model = list(model_choices.keys())[0] if model_choices else ""

        provider_names = {
            AI_PROVIDER_OPENAI: "OpenAI",
            AI_PROVIDER_ANTHROPIC: "Anthropic",
            AI_PROVIDER_GOOGLE: "Google",
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_AI_MODEL, default=default_model): vol.In(model_choices),
            }
        )

        return self.async_show_form(
            step_id="api_key",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "provider": provider_names.get(provider, provider),
            },
        )

    async def _async_validate_api_key(
        self, provider: str, api_key: str, model: str
    ) -> bool:
        """Validate the API key with a test request."""
        if not api_key:
            return False

        try:
            from .ai_provider import create_ai_provider

            ai = create_ai_provider(self.hass, provider, api_key, model)
            return await ai.async_test_connection()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("API key validation failed: %s", err)
            return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AIDashboardOptionsFlow:
        """Return the options flow handler."""
        return AIDashboardOptionsFlow(config_entry)


class AIDashboardOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for AI Dashboard."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_options = self.config_entry.options
        current_data = self.config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AI_PROVIDER,
                    default=current_data.get(CONF_AI_PROVIDER, AI_PROVIDER_OFFLINE),
                ): vol.In(AI_PROVIDERS),
                vol.Optional(
                    CONF_API_KEY,
                    default=current_data.get(CONF_API_KEY, ""),
                ): str,
                vol.Optional(
                    CONF_DASHBOARD_TITLE,
                    default=current_data.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE),
                ): str,
                vol.Required(
                    CONF_USE_MUSHROOM,
                    default=current_options.get(CONF_USE_MUSHROOM, True),
                ): bool,
                vol.Required(
                    CONF_LANGUAGE,
                    default=current_options.get(CONF_LANGUAGE, "de"),
                ): vol.In({"de": "Deutsch", "en": "English"}),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
