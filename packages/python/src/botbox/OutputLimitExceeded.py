class OutputLimitExceeded(Exception):
    """The agent printed a line longer than botbox will hold, so botbox ended its session."""
