"""botbox - run a coding agent inside a locked-down Docker container."""

from adocker import DockerException
from botbox.agents import Agent, ClaudeAgent, CodexAgent, HomeFiles, Message, PiAgent
from botbox.Botbox import Botbox
from botbox.credential_proxy import Credential, CredentialsExpired, CredentialSource, Injection
from botbox.RunResult import RunResult
from botbox.Timeout import Timeout

__all__ = [
    "Agent",
    "Botbox",
    "ClaudeAgent",
    "CodexAgent",
    "Credential",
    "CredentialSource",
    "CredentialsExpired",
    "DockerException",
    "HomeFiles",
    "Injection",
    "Message",
    "PiAgent",
    "RunResult",
    "Timeout",
]
