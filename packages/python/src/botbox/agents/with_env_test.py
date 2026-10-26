from botbox.agents.with_env import with_env


def describe_with_env() -> None:
    def it_leaves_the_command_alone_without_env() -> None:
        assert with_env({}, "claude -p hi") == "claude -p hi"

    def it_prefixes_each_var_in_order() -> None:
        assert with_env({"A": "1", "B": "2"}, "claude -p hi") == "A=1 B=2 claude -p hi"

    def it_quotes_values_for_the_shell() -> None:
        assert with_env({"A": "x y;$(z)"}, "cmd") == "A='x y;$(z)' cmd"
