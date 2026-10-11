"""botbox - run a coding agent inside a locked-down Docker container."""

from botbox.agents import Agent, ClaudeAgent, PiAgent
from botbox.Botbox import Botbox
from botbox.RunResult import RunResult

__all__ = ["Agent", "Botbox", "ClaudeAgent", "PiAgent", "RunResult"]
