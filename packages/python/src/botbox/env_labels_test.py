import pytest

from botbox.env_labels import env_labels

PATH = "/tmp/runs/2026-10-27T14:38:00-ab12"


def describe_env_labels() -> None:
    def it_is_empty_without_the_variable() -> None:
        assert env_labels({}) == {}

    def it_is_empty_for_an_empty_variable() -> None:
        assert env_labels({"BOTBOX_LABELS": ""}) == {}

    def it_reads_one_label_per_line_split_on_the_first_equals() -> None:
        environ = {"BOTBOX_LABELS": f"a.run={PATH}\n\nb=x=y\n"}
        assert env_labels(environ) == {"a.run": PATH, "b": "x=y"}

    def it_refuses_a_line_without_equals() -> None:
        with pytest.raises(ValueError, match="key=value"):
            env_labels({"BOTBOX_LABELS": "nope"})

    def it_reserves_the_cleanup_label() -> None:
        with pytest.raises(ValueError, match=r"botbox\.run"):
            env_labels({"BOTBOX_LABELS": "botbox.run=other"})
