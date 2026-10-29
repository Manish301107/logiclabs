"""Browser-local persistence for each visitor's optional Gemini API key."""
from __future__ import annotations

from typing import Any

import streamlit as st

COMPONENT_STATE_KEY = "logiclab_api_key_storage"
API_KEY_STORAGE_KEY = "logiclab_gemini_api_key_v1"
SETUP_STORAGE_KEY = "logiclab_gemini_setup_done_v1"

_INITIAL_STATE = {
    "ready": False,
    "api_key": None,
    "setup_done": False,
    "error": None,
    "command_id": None,
}

_STORAGE_COMPONENT = st.components.v2.component(
    "logiclab.browser_api_key_storage",
    html="<div aria-hidden='true'></div>",
    js="""
export default function (component) {
  const { data, setStateValue } = component
  const command = data.command
  const commandId = command?.id ?? null

  try {
    if (command?.action === "save") {
      localStorage.setItem(data.apiKeyStorageKey, command.apiKey)
      localStorage.setItem(data.setupStorageKey, "true")
    } else if (command?.action === "skip") {
      localStorage.setItem(data.setupStorageKey, "true")
    } else if (command?.action === "clear") {
      localStorage.removeItem(data.apiKeyStorageKey)
      localStorage.setItem(data.setupStorageKey, "true")
    }

    const next = {
      ready: true,
      api_key: localStorage.getItem(data.apiKeyStorageKey),
      setup_done: localStorage.getItem(data.setupStorageKey) === "true",
      error: null,
      command_id: commandId,
    }
    if (JSON.stringify(data.current) !== JSON.stringify(next)) {
      setStateValue("value", next)
    }
  } catch {
    const next = {
      ready: true,
      api_key: null,
      setup_done: false,
      error: "Browser storage is unavailable. Your key can only be used for this visit.",
      command_id: commandId,
    }
    if (JSON.stringify(data.current) !== JSON.stringify(next)) {
      setStateValue("value", next)
    }
  }
}
""",
)


def mount_api_key_storage(command: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mount the browser storage bridge and return its latest state."""
    component_state = st.session_state.get(COMPONENT_STATE_KEY, {})
    current = component_state.get("value", _INITIAL_STATE)
    result = _STORAGE_COMPONENT(
        key=COMPONENT_STATE_KEY,
        data={
            "apiKeyStorageKey": API_KEY_STORAGE_KEY,
            "setupStorageKey": SETUP_STORAGE_KEY,
            "command": command,
            "current": current,
        },
        default={"value": _INITIAL_STATE},
        on_value_change=lambda: None,
        width="content",
        height="1px",
    )
    value = result.value
    return value if isinstance(value, dict) else _INITIAL_STATE.copy()
