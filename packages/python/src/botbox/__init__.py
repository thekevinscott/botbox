"""botbox - run a coding agent inside a locked-down Docker container."""

from botbox.agents import Agent, ClaudeAgent, CodexAgent, PiAgent, SessionAgent
from botbox.Botbox import Botbox
from botbox.docker.DockerException import DockerException
from botbox.reap import reap
from botbox.RunResult import RunResult
from botbox.Session import Session
from botbox.Timeout import Timeout

__all__ = [
    "Agent",
    "Botbox",
    "ClaudeAgent",
    "CodexAgent",
    "DockerException",
    "PiAgent",
    "RunResult",
    "Session",
    "SessionAgent",
    "Timeout",
    "reap",
]
