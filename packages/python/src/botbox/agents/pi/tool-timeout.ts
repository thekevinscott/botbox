// Loaded by `pi -e`. Caps every bash call at BOTBOX_TOOL_TIMEOUT seconds, whatever the model asks.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const limit = Number(process.env.BOTBOX_TOOL_TIMEOUT);
  if (!(limit > 0)) return;
  pi.on("tool_call", (event) => {
    if (event.toolName !== "bash") return;
    const input = event.input as { timeout?: number };
    const asked = input.timeout;
    input.timeout = typeof asked === "number" && asked > 0 ? Math.min(asked, limit) : limit;
  });
}
