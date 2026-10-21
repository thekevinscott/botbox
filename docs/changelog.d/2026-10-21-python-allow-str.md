**Changed**: `Botbox(allow="github.com")` raises `TypeError` and names the tuple to pass. Before, the string was split into its characters, so the host was quietly never allowed.
