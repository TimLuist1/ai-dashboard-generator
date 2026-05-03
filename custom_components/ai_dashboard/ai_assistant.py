"""AI Assistant for Home Assistant.

The assistant receives the full HA context and can call any registered tool
(call_service, create_automation, rename_entity, …) via provider tool-calling APIs.

Supported providers: OpenAI (function calling), Anthropic (tool use), Google Gemini
(function declarations), and a limited offline/rule-based fallback.

Conversation flow
─────────────────
1. User sends a message.
2. HA context is built and injected into the system prompt.
3. AI responds with text and/or one or more tool calls.
4. Tool calls are either:
   • Executed immediately (read-only tools, or when auto_execute=True).
   • Returned as "pending actions" that the user must confirm first.
5. After execution, tool results are fed back to the AI and the cycle repeats
   until the AI produces a final text-only response (no more tool calls).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6
MAX_HISTORY_MESSAGES = 30


@dataclass
class ActionItem:
    """A tool call proposed or executed by the AI."""

    tool_name: str
    tool_call_id: str
    tool_args: dict
    description: str
    is_destructive: bool = False
    executed: bool = False
    result: dict | None = None


class AIAssistant:
    """AI Assistant with full HA read/write access via tool calling."""

    def __init__(
        self,
        hass: "HomeAssistant",
        provider: str,
        api_key: str,
        model: str,
        language: str = "de",
    ) -> None:
        self.hass = hass
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.language = language
        self._context_builder: HAContextBuilder | None = None
        self._tool_executor: HAToolExecutor | None = None
        self._history: list[dict] = []  # raw provider-agnostic messages

    @property
    def _context(self) -> HAContextBuilder:
        if self._context_builder is None:
            from .ha_context import HAContextBuilder
            self._context_builder = HAContextBuilder(self.hass)
        return self._context_builder

    @property
    def _tools(self) -> HAToolExecutor:
        if self._tool_executor is None:
            from .ha_tools import HAToolExecutor
            self._tool_executor = HAToolExecutor(self.hass)
        return self._tool_executor

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    async def async_chat(
        self,
        user_message: str,
        auto_execute: bool = False,
        context_depth: str = "standard",
    ) -> dict:
        """Process a user message and return the AI's response.

        Returns:
            {
                "message": str,                  # AI response text
                "actions": list[dict],           # Pending (unconfirmed) actions
                "executed_actions": list[dict],  # Already executed actions
                "requires_confirmation": bool,
            }
        """
        # Build HA context once per request
        ha_context = await self._context.async_build(
            include_states=True,
            max_entities=300 if context_depth == "full" else 150,
        )
        context_summary = self._context.build_compact_summary(ha_context)
        system_prompt = self._build_system_prompt(context_summary)

        # Append user message to history
        self._history.append({"role": "user", "content": user_message})

        # Trim to keep within token budget
        if len(self._history) > MAX_HISTORY_MESSAGES:
            self._history = self._history[-MAX_HISTORY_MESSAGES:]

        pending_actions: list[ActionItem] = []
        executed_actions: list[ActionItem] = []
        final_message = ""

        # Working copy of messages for this turn
        messages = list(self._history)
        iterations = 0

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1

            try:
                response = await self._call_provider(system_prompt, messages)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error("AI provider call failed: %s", err)
                final_message = f"Fehler beim KI-Aufruf: {err}"
                break

            tool_calls: list[dict] = response.get("tool_calls", [])
            text_content: str = response.get("content", "") or ""

            if not tool_calls:
                # No more tools → final answer
                final_message = text_content
                self._history.append({"role": "assistant", "content": final_message})
                break

            # Build assistant message for history (with tool calls)
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": text_content,
                "tool_calls": tool_calls,
            }
            messages.append(assistant_msg)

            tool_results: list[dict] = []

            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                call_id = tc.get("id", tool_name)

                is_destructive = self._tools.is_destructive(tool_name)
                action = ActionItem(
                    tool_name=tool_name,
                    tool_call_id=call_id,
                    tool_args=tool_args,
                    description=self._describe_action(tool_name, tool_args),
                    is_destructive=is_destructive,
                )

                if auto_execute or not is_destructive:
                    # Execute immediately
                    result = await self._tools.async_execute(tool_name, tool_args)
                    action.executed = True
                    action.result = result
                    executed_actions.append(action)
                    tool_results.append(
                        {
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "result": json.dumps(result, ensure_ascii=False),
                        }
                    )
                else:
                    # Queue for user confirmation
                    pending_actions.append(action)
                    tool_results.append(
                        {
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "result": json.dumps(
                                {
                                    "pending": True,
                                    "message": "Warte auf Benutzerbestätigung.",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )

            messages.append({"role": "tool", "tool_results": tool_results})

            # If there are unconfirmed actions, pause and return to user
            if pending_actions and not auto_execute:
                final_message = text_content
                break

        requires_confirmation = bool(pending_actions) and not auto_execute

        return {
            "message": final_message,
            "actions": [
                {
                    "tool_name": a.tool_name,
                    "tool_call_id": a.tool_call_id,
                    "args": a.tool_args,
                    "description": a.description,
                    "is_destructive": a.is_destructive,
                }
                for a in pending_actions
            ],
            "executed_actions": [
                {
                    "tool_name": a.tool_name,
                    "description": a.description,
                    "result": a.result,
                    "success": not bool(a.result and a.result.get("error")),
                }
                for a in executed_actions
            ],
            "requires_confirmation": requires_confirmation,
        }

    async def async_execute_confirmed_actions(
        self, actions: list[dict]
    ) -> list[dict]:
        """Execute actions that the user has confirmed."""
        results = []
        for action_data in actions:
            result = await self._tools.async_execute(
                action_data["tool_name"],
                action_data["args"],
            )
            results.append(
                {
                    "tool_name": action_data["tool_name"],
                    "description": action_data["description"],
                    "result": result,
                    "success": not bool(result.get("error")),
                }
            )
        return results

    def clear_history(self) -> None:
        self._history = []

    def get_history(self) -> list[dict]:
        return [
            {"role": m["role"], "content": m.get("content", "")}
            for m in self._history
            if m["role"] in ("user", "assistant")
        ]

    # ─────────────────────────────────────────────────────────────
    # Provider dispatching
    # ─────────────────────────────────────────────────────────────

    async def _call_provider(self, system_prompt: str, messages: list[dict]) -> dict:
        from .const import (
            AI_PROVIDER_ANTHROPIC,
            AI_PROVIDER_GOOGLE,
            AI_PROVIDER_OPENAI,
        )

        if self.provider == AI_PROVIDER_OPENAI:
            return await self._call_openai(system_prompt, messages)
        if self.provider == AI_PROVIDER_ANTHROPIC:
            return await self._call_anthropic(system_prompt, messages)
        if self.provider == AI_PROVIDER_GOOGLE:
            return await self._call_google(system_prompt, messages)
        return await self._offline_response(messages)

    # ─────────────────────────────────────────────────────────────
    # OpenAI
    # ─────────────────────────────────────────────────────────────

    async def _call_openai(self, system_prompt: str, messages: list[dict]) -> dict:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        from .ha_tools import TOOL_DEFINITIONS

        session = async_get_clientsession(self.hass)

        openai_msgs: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg["role"]
            if role == "user":
                openai_msgs.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                m: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                }
                if msg.get("tool_calls"):
                    m["tool_calls"] = [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for i, tc in enumerate(msg["tool_calls"])
                    ]
                openai_msgs.append(m)
            elif role == "tool":
                for tr in msg.get("tool_results", []):
                    openai_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tr["tool_call_id"],
                            "content": tr["result"],
                        }
                    )

        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model or "gpt-4o-mini",
                "messages": openai_msgs,
                "tools": TOOL_DEFINITIONS,
                "tool_choice": "auto",
                "max_tokens": 2000,
                "temperature": 0.3,
            },
            timeout=60,
        ) as resp:
            if resp.status != 200:
                raise ValueError(
                    f"OpenAI Fehler {resp.status}: {(await resp.text())[:200]}"
                )
            data = await resp.json()

        message = data["choices"][0]["message"]
        result: dict[str, Any] = {"content": message.get("content") or ""}
        if message.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "args": json.loads(tc["function"]["arguments"]),
                }
                for tc in message["tool_calls"]
            ]
        return result

    # ─────────────────────────────────────────────────────────────
    # Anthropic
    # ─────────────────────────────────────────────────────────────

    async def _call_anthropic(self, system_prompt: str, messages: list[dict]) -> dict:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        from .ha_tools import get_anthropic_tools

        session = async_get_clientsession(self.hass)

        anthropic_msgs: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                anthropic_msgs.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                content: list[dict] = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg.get("tool_calls", []):
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", tc["name"]),
                            "name": tc["name"],
                            "input": tc["args"],
                        }
                    )
                anthropic_msgs.append({"role": "assistant", "content": content})
            elif role == "tool":
                content = [
                    {
                        "type": "tool_result",
                        "tool_use_id": tr["tool_call_id"],
                        "content": tr["result"],
                    }
                    for tr in msg.get("tool_results", [])
                ]
                anthropic_msgs.append({"role": "user", "content": content})

        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model or "claude-3-5-haiku-20241022",
                "system": system_prompt,
                "messages": anthropic_msgs,
                "tools": get_anthropic_tools(),
                "max_tokens": 2000,
            },
            timeout=60,
        ) as resp:
            if resp.status != 200:
                raise ValueError(
                    f"Anthropic Fehler {resp.status}: {(await resp.text())[:200]}"
                )
            data = await resp.json()

        result: dict[str, Any] = {"content": "", "tool_calls": []}
        for block in data.get("content", []):
            if block["type"] == "text":
                result["content"] += block["text"]
            elif block["type"] == "tool_use":
                result["tool_calls"].append(
                    {"id": block["id"], "name": block["name"], "args": block["input"]}
                )
        if not result["tool_calls"]:
            del result["tool_calls"]
        return result

    # ─────────────────────────────────────────────────────────────
    # Google Gemini
    # ─────────────────────────────────────────────────────────────

    async def _call_google(self, system_prompt: str, messages: list[dict]) -> dict:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        from .ha_tools import get_google_tools

        session = async_get_clientsession(self.hass)
        model = self.model or "gemini-2.0-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.api_key}"
        )

        gemini_contents: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                gemini_contents.append(
                    {"role": "user", "parts": [{"text": msg["content"]}]}
                )
            elif role == "assistant":
                parts: list[dict] = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                for tc in msg.get("tool_calls", []):
                    parts.append(
                        {"functionCall": {"name": tc["name"], "args": tc["args"]}}
                    )
                gemini_contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                parts = [
                    {
                        "functionResponse": {
                            "name": tr["name"],
                            "response": {"result": tr["result"]},
                        }
                    }
                    for tr in msg.get("tool_results", [])
                ]
                gemini_contents.append({"role": "user", "parts": parts})

        async with session.post(
            url,
            json={
                "contents": gemini_contents,
                "tools": [{"functionDeclarations": get_google_tools()}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"maxOutputTokens": 2000, "temperature": 0.3},
            },
            timeout=60,
        ) as resp:
            if resp.status != 200:
                raise ValueError(
                    f"Google Fehler {resp.status}: {(await resp.text())[:200]}"
                )
            data = await resp.json()

        parts = data["candidates"][0].get("content", {}).get("parts", [])
        result: dict[str, Any] = {"content": "", "tool_calls": []}
        for part in parts:
            if "text" in part:
                result["content"] += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                result["tool_calls"].append(
                    {"id": fc["name"], "name": fc["name"], "args": fc.get("args", {})}
                )
        if not result["tool_calls"]:
            del result["tool_calls"]
        return result

    # ─────────────────────────────────────────────────────────────
    # Offline fallback
    # ─────────────────────────────────────────────────────────────

    async def _offline_response(self, messages: list[dict]) -> dict:
        return {
            "content": (
                "Der KI-Assistent ist im Offline-Modus nicht verfügbar.\n\n"
                "Bitte konfiguriere einen API-Schlüssel unter **Einstellungen** "
                "(OpenAI, Anthropic oder Google Gemini), um den Assistenten nutzen zu können."
            )
        }

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _build_system_prompt(self, ha_context: str) -> str:
        de = self.language == "de"
        now = datetime.now().strftime("%d.%m.%Y %H:%M")

        if de:
            return (
                f"Du bist ein intelligenter Home Assistant Assistent. "
                f"Heute ist {now}.\n\n"
                "Du hast Vollzugriff auf das Home Assistant System und kannst:\n"
                "- Services aufrufen (Lichter, Heizung, Medien, Rolläden, Schlösser, …)\n"
                "- Automationen und Szenen erstellen\n"
                "- Entities umbenennen und Bereichen zuweisen\n"
                "- Dashboards generieren\n"
                "- Entity-Details und Verlauf abrufen\n"
                "- Entities suchen\n\n"
                "Antworte immer auf Deutsch. Sei präzise und hilfreich.\n"
                "Erkläre was du tust, bevor du Aktionen ausführst.\n"
                "Wenn du dir bei einer Entity-ID nicht sicher bist, nutze das find_entities-Tool.\n\n"
                "## Aktuelle Home Assistant Konfiguration\n\n"
                f"{ha_context}"
            )
        return (
            f"You are an intelligent Home Assistant assistant. "
            f"Today is {now}.\n\n"
            "You have full access to the Home Assistant system and can:\n"
            "- Call services (lights, heating, media, covers, locks, …)\n"
            "- Create automations and scenes\n"
            "- Rename entities and assign them to areas\n"
            "- Generate dashboards\n"
            "- Retrieve entity details and history\n"
            "- Search for entities\n\n"
            "Always respond in English. Be precise and helpful.\n"
            "Explain what you are doing before executing actions.\n"
            "If you are unsure about an entity_id, use the find_entities tool first.\n\n"
            "## Current Home Assistant Configuration\n\n"
            f"{ha_context}"
        )

    @staticmethod
    def _describe_action(tool_name: str, args: dict) -> str:
        descriptions = {
            "call_service": lambda a: (
                f"Service {a.get('domain','?')}.{a.get('service','?')} aufrufen"
                + (f" für {a['entity_id']}" if a.get("entity_id") else "")
            ),
            "create_automation": lambda a: f"Automation erstellen: '{a.get('alias','?')}'",
            "create_scene": lambda a: f"Szene erstellen: '{a.get('name','?')}'",
            "rename_entity": lambda a: (
                f"Entity '{a.get('entity_id','?')}' umbenennen → '{a.get('new_name','?')}'"
            ),
            "assign_area": lambda a: (
                f"Entity '{a.get('entity_id','?')}' → Bereich '{a.get('area_id','?')}'"
            ),
            "get_entity_history": lambda a: f"Verlauf von '{a.get('entity_id','?')}' abrufen",
            "generate_dashboard": lambda a: "Dashboard generieren"
            + (" und anwenden" if a.get("auto_apply") else ""),
            "get_entity_details": lambda a: f"Details von '{a.get('entity_id','?')}'",
            "find_entities": lambda a: "Entities suchen: " + str(
                {k: v for k, v in a.items() if v}
            ),
        }
        fn = descriptions.get(tool_name)
        return fn(args) if fn else f"{tool_name}({args})"
