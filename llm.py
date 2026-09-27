"""
Local LLM layer for JARVIS using Ollama.

Uses Ollama's native tool-calling API.

Flow:

    user
      ↓
    Qwen3
      ↓
    native tool_calls
      ↓
    tools.py
      ↓
    tool result
      ↓
    Qwen3
      ↓
    final spoken response
"""

import requests

from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    LLM_TEMPERATURE,
    MAX_HISTORY_TURNS,
    ASSISTANT_NAME,
)

from tools import TOOL_REGISTRY


SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME}, a concise, capable voice assistant
running locally on the user's Windows computer.

Speak naturally and briefly. Your replies are read aloud, so avoid markdown,
lists, or long paragraphs. Get to the point in 1-3 sentences unless the user
asks for detail.

Use the available tools when they are needed to answer the user's request.

Do not describe a tool call to the user. When a tool is needed, call the
appropriate tool directly.
"""


# ---------------------------------------------------------------------------
# Native Ollama tool definitions
# ---------------------------------------------------------------------------

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Launch a desktop application on the user's computer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "description": (
                            "Application name, for example notepad, "
                            "firefox, or code."
                        ),
                    }
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command subject to JARVIS's Windows safety "
                "checks and allowed-command rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the text file.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory path. Defaults to the current "
                            "directory if omitted."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "City or location, for example Chennai."
                        ),
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_stats",
            "description": (
                "Report CPU, memory, disk, battery, and NVIDIA GPU status."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


class Conversation:
    """Keeps a rolling window of chat history."""

    def __init__(self):
        self.turns = []

    def add(self, role: str, content: str):
        self.turns.append({
            "role": role,
            "content": content,
        })

        max_messages = MAX_HISTORY_TURNS * 2

        if len(self.turns) > max_messages:
            self.turns = self.turns[-max_messages:]

    def as_ollama_messages(self):
        return list(self.turns)


def _call_ollama(messages):
    """
    Call Ollama and return the complete message object.

    Returning the complete message is important because native tool calls
    are stored in message["tool_calls"].
    """

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            *messages,
        ],
        "tools": OLLAMA_TOOLS,
        "stream": False,
        "options": {
            "temperature": LLM_TEMPERATURE,
        },
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=180,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not contact Ollama at {OLLAMA_URL}: {exc}"
        ) from exc

    try:
        data = response.json()

    except ValueError as exc:
        raise RuntimeError(
            "Ollama returned invalid JSON."
        ) from exc

    try:
        return data["message"]

    except (KeyError, TypeError):
        raise RuntimeError(
            f"Ollama returned an unexpected response: {data}"
        )


def _execute_tool_calls(tool_calls):
    """
    Execute native Ollama tool calls.

    Returns a list of Ollama-compatible tool messages.
    """

    tool_messages = []

    for tool_call in tool_calls:
        function = tool_call.get("function", {})

        tool_name = function.get("name")
        tool_args = function.get("arguments", {})

        if not tool_name:
            continue

        if not isinstance(tool_args, dict):
            tool_args = {}

        if tool_name not in TOOL_REGISTRY:
            tool_result = (
                f"I don't have access to a tool called '{tool_name}'."
            )

        else:
            try:
                tool_result = TOOL_REGISTRY[tool_name](tool_args)

            except Exception as exc:
                tool_result = (
                    f"Tool '{tool_name}' failed: {exc}"
                )

        tool_messages.append({
            "role": "tool",
            "content": str(tool_result),
        })

    return tool_messages


def ask(conversation: Conversation, user_text: str) -> str:
    """
    Send a user request to Ollama.

    If Qwen3 requests tools, execute them and send the results back to
    Qwen3. Otherwise return the normal conversational response.
    """

    conversation.add(
        "user",
        user_text,
    )

    # ---------------------------------------------------------------
    # First LLM call
    # ---------------------------------------------------------------

    assistant_message = _call_ollama(
        conversation.as_ollama_messages()
    )

    tool_calls = assistant_message.get("tool_calls") or []

    # ---------------------------------------------------------------
    # Normal conversational response
    # ---------------------------------------------------------------

    if not tool_calls:
        reply = (
            assistant_message.get("content") or ""
        ).strip()

        conversation.add(
            "assistant",
            reply,
        )

        return reply

    # ---------------------------------------------------------------
    # Native tool call
    # ---------------------------------------------------------------

    # Preserve the assistant's native tool-call message in the
    # conversation history.

    conversation.turns.append({
        "role": "assistant",
        "content": assistant_message.get("content", ""),
        "tool_calls": tool_calls,
    })

    # Execute requested tools.

    tool_messages = _execute_tool_calls(
        tool_calls
    )

    # Add tool results to conversation.

    conversation.turns.extend(
        tool_messages
    )

    # ---------------------------------------------------------------
    # Second LLM call
    # ---------------------------------------------------------------

    final_message = _call_ollama(
        conversation.as_ollama_messages()
    )

    final_reply = (
        final_message.get("content") or ""
    ).strip()

    conversation.add(
        "assistant",
        final_reply,
    )

    return final_reply