"""Aurelius agent: single agent with tools.

Uses Amazon Nova (Bedrock) by default. For Groq (Llama), change the import to runtime_groq.
"""
#from agent.runtime_groq import run_chat
from agent.runtime_nova import run_chat

__all__ = ["run_chat"]
