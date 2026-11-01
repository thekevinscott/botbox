"""The pi image's wrapper runs a producer through the shipped stdout filter."""

import os
import subprocess
from pathlib import Path

PI_DIR = Path(__file__).parents[2] / "src" / "botbox" / "agents" / "pi"


def describe_pi_wrapper() -> None:
    def it_filters_events_but_keeps_pi_status_and_stderr(tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "pi"
        wrapper.write_bytes((PI_DIR / "pi-wrapper").read_bytes())
        wrapper.chmod(0o755)
        producer = bin_dir / "pi-unfiltered"
        producer.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' '{\"type\":\"tool_execution_update\"}' "
            '\'{"type":"tool_execution_end"}\'\n'
            "printf 'error: %s\\n' \"$1\" >&2\n"
            "exit 17\n"
        )
        producer.chmod(0o755)
        filter_dir = tmp_path / "lib" / "botbox"
        filter_dir.mkdir(parents=True)
        (filter_dir / "filter-pi-stdout.py").write_bytes((PI_DIR / "filter_stdout.py").read_bytes())
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        done = subprocess.run(["sh", "-c", "pi 'a b'"], env=env, capture_output=True, text=True)
        assert done.returncode == 17
        assert done.stdout == '{"type":"tool_execution_end"}\n'
        assert done.stderr == "error: a b\n"
