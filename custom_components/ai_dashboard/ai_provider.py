"""AI provider module for AI Dashboard Generator.

Supports: Offline (rule-based), OpenAI, Anthropic, Google Gemini.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def async_test_connection(self) -> bool:
        """Test if the API connection works."""

    @abstractmethod
    async def async_analyze_entities(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Analyze entities and return enriched data with names and suggestions."""

    @abstractmethod
    async def async_generate_dashboard_hints(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Generate high-level dashboard hints (room descriptions, colors)."""


class OfflineAIProvider(AIProvider):
    """Rule-based offline AI provider - no API key required."""

    async def async_test_connection(self) -> bool:
        """Always available offline."""
        return True

    async def async_analyze_entities(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Analyze entities using rule-based approach."""
        result = {}
        for area in areas_data:
            area_id = area["area_id"]
            result[area_id] = {
                "icon": area.get("icon"),
                "color": self._get_area_color(area["name"]),
                "entities": {},
            }
            for entity in area.get("entities", []):
                result[area_id]["entities"][entity["entity_id"]] = {
                    "friendly_name": entity.get("suggested_name") or entity.get("friendly_name"),
                    "icon": entity.get("suggested_icon") or entity.get("icon"),
                    "visible": True,
                }
        return result

    async def async_generate_dashboard_hints(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Return basic hints without AI."""
        return {
            "overview_subtitle": "Mein Zuhause" if language == "de" else "My Home",
            "areas": {
                area["area_id"]: {
                    "subtitle": self._get_area_subtitle(area, language)
                }
                for area in areas_data
            },
        }

    def _get_area_color(self, area_name: str) -> str:
        """Return a color for an area based on its name."""
        name_lower = area_name.lower()
        color_map = {
            "wohnzimmer": "orange",
            "living": "orange",
            "salon": "orange",
            "schlafzimmer": "indigo",
            "bedroom": "indigo",
            "küche": "green",
            "kitchen": "green",
            "bad": "blue",
            "bathroom": "blue",
            "büro": "teal",
            "office": "teal",
            "keller": "grey",
            "basement": "grey",
            "garten": "green",
            "garden": "green",
            "garage": "brown",
            "kinderzimmer": "pink",
            "kids": "pink",
            "children": "pink",
            "esszimmer": "amber",
            "dining": "amber",
            "flur": "cyan",
            "hallway": "cyan",
            "corridor": "cyan",
        }
        for key, color in color_map.items():
            if key in name_lower:
                return color
        return "blue-grey"

    def _get_area_subtitle(self, area: dict, language: str) -> str:
        """Generate a subtitle for an area."""
        counts = area.get("entity_counts", {})
        parts = []
        if counts.get("light", 0) > 0:
            n = counts["light"]
            if language == "de":
                parts.append(f"{n} {'Licht' if n == 1 else 'Lichter'}")
            else:
                parts.append(f"{n} {'light' if n == 1 else 'lights'}")
        if counts.get("climate", 0) > 0:
            if language == "de":
                parts.append("Heizung")
            else:
                parts.append("Heating")
        if counts.get("sensor", 0) > 0:
            n = counts["sensor"]
            if language == "de":
                parts.append(f"{n} {'Sensor' if n == 1 else 'Sensoren'}")
            else:
                parts.append(f"{n} {'sensor' if n == 1 else 'sensors'}")
        return " · ".join(parts) if parts else ""


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, hass: HomeAssistant, api_key: str, model: str) -> None:
        """Initialize OpenAI provider."""
        self.hass = hass
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"

    async def async_test_connection(self) -> bool:
        """Test API connection."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5,
                },
                timeout=10,
            ) as resp:
                return resp.status == 200
        except Exception:  # pylint: disable=broad-except
            return False

    async def async_analyze_entities(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Use GPT to analyze and improve entity names."""
        prompt = self._build_analysis_prompt(areas_data, language)

        try:
            response_text = await self._async_call_api(prompt)
            return self._parse_json_response(response_text)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("OpenAI analysis failed, using offline fallback: %s", err)
            offline = OfflineAIProvider()
            return await offline.async_analyze_entities(areas_data, language)

    async def async_generate_dashboard_hints(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Generate dashboard hints via GPT."""
        prompt = self._build_hints_prompt(areas_data, language)

        try:
            response_text = await self._async_call_api(prompt)
            return self._parse_json_response(response_text)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("OpenAI hints failed, using offline fallback: %s", err)
            offline = OfflineAIProvider()
            return await offline.async_generate_dashboard_hints(areas_data, language)

    def _build_analysis_prompt(self, areas_data: list[dict], language: str) -> str:
        """Build the entity analysis prompt."""
        lang_instruction = (
            "Antworte auf Deutsch." if language == "de" else "Respond in English."
        )

        entities_summary = []
        for area in areas_data[:10]:  # Limit to avoid token overflow
            for entity in area.get("entities", [])[:20]:
                entities_summary.append(
                    f"- {entity['entity_id']} "
                    f"(aktuell: {entity.get('suggested_name', entity['friendly_name'])}, "
                    f"domain: {entity['domain']}, "
                    f"class: {entity.get('device_class', 'keine')}, "
                    f"area: {area['name']})"
                )

        return f"""Du bist ein Home Assistant Dashboard Experte.
{lang_instruction}

Ich habe folgende Home Assistant Entities. Verbessere die Anzeigenamen und schlage passende Icons vor.

Entities:
{chr(10).join(entities_summary[:100])}

Antworte NUR mit validem JSON (kein Markdown, keine Erklärungen):
{{
  "AREA_ID": {{
    "icon": "mdi:sofa",
    "color": "orange",
    "entities": {{
      "entity.id": {{
        "friendly_name": "Verbesserter Name",
        "icon": "mdi:lightbulb",
        "visible": true
      }}
    }}
  }}
}}

Verwende nur mdi: Icons. Farben: red, pink, purple, deep-purple, indigo, blue, light-blue, cyan, teal, green, light-green, lime, yellow, amber, orange, deep-orange, brown, grey, blue-grey."""

    def _build_hints_prompt(self, areas_data: list[dict], language: str) -> str:
        """Build the dashboard hints prompt."""
        lang_instruction = (
            "Antworte auf Deutsch." if language == "de" else "Respond in English."
        )

        area_list = [
            f"- {area['name']} ({area.get('relevant_entities', 0)} Entities)"
            for area in areas_data
        ]

        return f"""Du bist ein Smart Home Experte.
{lang_instruction}

Mein Haus hat diese Räume:
{chr(10).join(area_list)}

Erstelle kurze, ansprechende Untertitel für jeden Raum (max. 30 Zeichen).
Antworte NUR mit validem JSON:
{{
  "overview_subtitle": "Willkommen zu Hause",
  "areas": {{
    "AREA_ID": {{
      "subtitle": "3 Lichter · 21°C"
    }}
  }}
}}"""

    async def _async_call_api(self, prompt: str) -> str:
        """Call the OpenAI API."""
        session = async_get_clientsession(self.hass)
        async with session.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a Home Assistant dashboard expert. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 2000,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise ValueError(f"OpenAI API error {resp.status}: {error_text[:200]}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from AI response."""
        # Strip markdown code blocks if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return json.loads(text)


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, hass: HomeAssistant, api_key: str, model: str) -> None:
        """Initialize Anthropic provider."""
        self.hass = hass
        self.api_key = api_key
        self.model = model or "claude-3-5-haiku-20241022"

    async def async_test_connection(self) -> bool:
        """Test API connection."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                self.API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5,
                },
                timeout=10,
            ) as resp:
                return resp.status == 200
        except Exception:  # pylint: disable=broad-except
            return False

    async def async_analyze_entities(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Use Claude to analyze entities."""
        # Reuse OpenAI provider's prompts since they work for Claude too
        openai_provider = OpenAIProvider(self.hass, self.api_key, self.model)
        prompt = openai_provider._build_analysis_prompt(areas_data, language)

        try:
            response_text = await self._async_call_api(prompt)
            return openai_provider._parse_json_response(response_text)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Anthropic analysis failed, using offline fallback: %s", err)
            offline = OfflineAIProvider()
            return await offline.async_analyze_entities(areas_data, language)

    async def async_generate_dashboard_hints(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Generate hints via Claude."""
        openai_provider = OpenAIProvider(self.hass, self.api_key, self.model)
        prompt = openai_provider._build_hints_prompt(areas_data, language)

        try:
            response_text = await self._async_call_api(prompt)
            return openai_provider._parse_json_response(response_text)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Anthropic hints failed, using offline fallback: %s", err)
            offline = OfflineAIProvider()
            return await offline.async_generate_dashboard_hints(areas_data, language)

    async def _async_call_api(self, prompt: str) -> str:
        """Call the Anthropic API."""
        session = async_get_clientsession(self.hass)
        async with session.post(
            self.API_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "system": "You are a Home Assistant dashboard expert. Always respond with valid JSON only.",
            },
            timeout=30,
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise ValueError(f"Anthropic API error {resp.status}: {error_text[:200]}")
            data = await resp.json()
            return data["content"][0]["text"]


class GoogleAIProvider(AIProvider):
    """Google Gemini provider."""

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, hass: HomeAssistant, api_key: str, model: str) -> None:
        """Initialize Google provider."""
        self.hass = hass
        self.api_key = api_key
        self.model = model or "gemini-2.0-flash"

    async def async_test_connection(self) -> bool:
        """Test API connection."""
        try:
            session = async_get_clientsession(self.hass)
            url = self.API_URL.format(model=self.model)
            async with session.post(
                f"{url}?key={self.api_key}",
                json={
                    "contents": [{"parts": [{"text": "Hello"}]}],
                    "generationConfig": {"maxOutputTokens": 5},
                },
                timeout=10,
            ) as resp:
                return resp.status == 200
        except Exception:  # pylint: disable=broad-except
            return False

    async def async_analyze_entities(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Use Gemini to analyze entities."""
        openai_provider = OpenAIProvider(self.hass, self.api_key, self.model)
        prompt = openai_provider._build_analysis_prompt(areas_data, language)

        try:
            response_text = await self._async_call_api(prompt)
            return openai_provider._parse_json_response(response_text)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Google AI analysis failed, using offline fallback: %s", err)
            offline = OfflineAIProvider()
            return await offline.async_analyze_entities(areas_data, language)

    async def async_generate_dashboard_hints(
        self, areas_data: list[dict], language: str = "de"
    ) -> dict:
        """Generate hints via Gemini."""
        openai_provider = OpenAIProvider(self.hass, self.api_key, self.model)
        prompt = openai_provider._build_hints_prompt(areas_data, language)

        try:
            response_text = await self._async_call_api(prompt)
            return openai_provider._parse_json_response(response_text)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Google AI hints failed, using offline fallback: %s", err)
            offline = OfflineAIProvider()
            return await offline.async_generate_dashboard_hints(areas_data, language)

    async def _async_call_api(self, prompt: str) -> str:
        """Call the Google Gemini API."""
        session = async_get_clientsession(self.hass)
        url = self.API_URL.format(model=self.model)
        async with session.post(
            f"{url}?key={self.api_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 2000,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
                "systemInstruction": {
                    "parts": [
                        {
                            "text": "You are a Home Assistant dashboard expert. Always respond with valid JSON only."
                        }
                    ]
                },
            },
            timeout=30,
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise ValueError(f"Google AI error {resp.status}: {error_text[:200]}")
            data = await resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]


def create_ai_provider(
    hass: HomeAssistant,
    provider: str,
    api_key: str,
    model: str,
) -> AIProvider:
    """Factory function to create the appropriate AI provider."""
    from .const import AI_PROVIDER_OFFLINE, AI_PROVIDER_OPENAI, AI_PROVIDER_ANTHROPIC, AI_PROVIDER_GOOGLE

    if provider == AI_PROVIDER_OPENAI:
        return OpenAIProvider(hass, api_key, model)
    elif provider == AI_PROVIDER_ANTHROPIC:
        return AnthropicProvider(hass, api_key, model)
    elif provider == AI_PROVIDER_GOOGLE:
        return GoogleAIProvider(hass, api_key, model)
    else:
        return OfflineAIProvider()
