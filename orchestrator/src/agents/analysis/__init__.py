"""Analysis agents -- graph construction, timeline, and profile synthesis."""

# Import all analysis agents to trigger registration
from src.agents.analysis.graph_builder import GraphBuilderAgent
from src.agents.analysis.timeline_builder import TimelineBuilderAgent
from src.agents.analysis.profile_synth import ProfileSynthAgent

__all__ = [
    "GraphBuilderAgent",
    "TimelineBuilderAgent",
    "ProfileSynthAgent",
]
