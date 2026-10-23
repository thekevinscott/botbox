"""botbox - run a coding agent inside a locked-down Docker container."""

from botbox.agents import Agent, ClaudeAgent, CodexAgent, PiAgent, SessionAgent
from botbox.Botbox import Botbox
from botbox.docker.DockerException import DockerException
from botbox.OutputLimitExceeded import OutputLimitExceeded
from botbox.reap import reap
from botbox.RunResult import RunResult
from botbox.Session import Session

__all__ = [
    "Agent",
    "Botbox",
    "ClaudeAgent",
    "CodexAgent",
    "DockerException",
    "OutputLimitExceeded",
    "PiAgent",
    "RunResult",
    "Session",
    "SessionAgent",
    "reap",
]
