"""Breach and exposure agents -- check for data leaks, infostealers, dark web mentions."""

# Import all breach agents to trigger registration
from src.agents.breach.hibp import HIBPAgent
from src.agents.breach.intelx import IntelXAgent
from src.agents.breach.hudsonrock import HudsonRockAgent
from src.agents.breach.ahmia import AhmiaAgent
from src.agents.breach.pastebin import PastebinAgent
from src.agents.breach.google_dorks import GoogleDorkAgent

__all__ = [
    "HIBPAgent",
    "IntelXAgent",
    "HudsonRockAgent",
    "AhmiaAgent",
    "PastebinAgent",
    "GoogleDorkAgent",
]
