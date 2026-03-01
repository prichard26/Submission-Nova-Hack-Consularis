"""Aurelius agent: single agent with tools. Re-exports for backward compatibility."""
from agent.runtime import run_chat
from agent.fallback import try_apply_message_update

__all__ = ["run_chat", "try_apply_message_update"]
