import dataclasses
import json
from typing import Any

import pytest

from botbox.credential_proxy.envoy_config import (
    SECRET_DIR,
    SECRET_FILE,
    SECRET_NAME,
    Injection,
    envoy_config,
)

CLAUDE = Injection(
    "api.anthropic.com", "/v1/messages(/count_tokens)?", "Authorization", ("x-api-key",)
)


def config(injection: Injection = CLAUDE, socket: str = "/run/botbox/credentials.sock") -> Any:
    return json.loads(envoy_config(injection, socket))


def manager(bootstrap: Any) -> Any:
    listener = bootstrap["static_resources"]["listeners"][0]
    return listener["filter_chains"][0]["filters"][0]["typed_config"]


def routes(bootstrap: Any) -> Any:
    return manager(bootstrap)["route_config"]["virtual_hosts"][0]["routes"]


def injector(bootstrap: Any) -> Any:
    return manager(bootstrap)["http_filters"][0]["typed_config"]["credential"]["typed_config"]


def cluster(bootstrap: Any) -> Any:
    return bootstrap["static_resources"]["clusters"][0]


def describe_Injection() -> None:
    def it_is_immutable() -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            CLAUDE.upstream = "other"  # type: ignore[misc]


def describe_envoy_config() -> None:
    def it_listens_on_the_socket_for_any_uid() -> None:
        pipe = config(socket="/s/c.sock")["static_resources"]["listeners"][0]["address"]["pipe"]
        assert pipe == {"path": "/s/c.sock", "mode": 0o666}

    def it_forwards_only_matching_paths_to_the_upstream() -> None:
        allowed, rest = routes(config())
        assert allowed["match"]["safe_regex"] == {"regex": "/v1/messages(/count_tokens)?"}
        assert allowed["route"]["cluster"] == cluster(config())["name"]
        assert allowed["route"]["host_rewrite_literal"] == "api.anthropic.com"
        assert rest["match"] == {"prefix": "/"}
        assert rest["direct_response"]["status"] == 403

    def it_forwards_only_post_by_default() -> None:
        allowed, _ = routes(config())
        assert allowed["match"]["headers"] == [
            {"name": ":method", "string_match": {"safe_regex": {"regex": "POST"}}}
        ]

    def it_forwards_any_of_the_given_methods() -> None:
        injection = Injection("chatgpt.com", "/x", "Authorization", methods=("GET", "POST"))
        allowed, _ = routes(config(injection))
        assert allowed["match"]["headers"] == [
            {"name": ":method", "string_match": {"safe_regex": {"regex": "GET|POST"}}}
        ]

    def it_never_times_out_a_streaming_response() -> None:
        allowed, _ = routes(config())
        assert allowed["route"]["timeout"] == "0s"

    def it_strips_the_named_headers() -> None:
        allowed, _ = routes(config())
        assert allowed["request_headers_to_remove"] == ["x-api-key"]

    def it_strips_nothing_by_default() -> None:
        injection = Injection("chatgpt.com", "/x", "Authorization")
        allowed, _ = routes(config(injection))
        assert allowed["request_headers_to_remove"] == []

    def it_replaces_the_header_from_the_watched_secret() -> None:
        filters = manager(config())["http_filters"]
        assert filters[0]["typed_config"]["overwrite"] is True
        assert filters[-1]["name"] == "envoy.filters.http.router"
        assert injector(config())["header"] == "Authorization"
        assert injector(config())["credential"] == {
            "name": SECRET_NAME,
            "sds_config": {
                "path_config_source": {
                    "path": SECRET_FILE,
                    "watched_directory": {"path": SECRET_DIR},
                }
            },
        }

    def it_keeps_the_secret_file_in_the_watched_directory() -> None:
        assert SECRET_FILE.startswith(f"{SECRET_DIR}/")

    def it_originates_tls_to_the_upstream_and_checks_its_name() -> None:
        upstream = cluster(config())
        address = upstream["load_assignment"]["endpoints"][0]["lb_endpoints"][0]
        assert address["endpoint"]["address"]["socket_address"] == {
            "address": "api.anthropic.com",
            "port_value": 443,
        }
        tls = upstream["transport_socket"]["typed_config"]
        assert tls["sni"] == "api.anthropic.com"
        assert tls["common_tls_context"]["validation_context"]["match_typed_subject_alt_names"] == [
            {"san_type": "DNS", "matcher": {"exact": "api.anthropic.com"}}
        ]

    def it_escapes_values_rather_than_splicing_them() -> None:
        injection = Injection("h", '/a"b\\d+', "X-Key")
        allowed, _ = routes(config(injection))
        assert allowed["match"]["safe_regex"]["regex"] == '/a"b\\d+'

    def it_leaves_no_placeholder() -> None:
        assert "__" not in envoy_config(CLAUDE, "/s")

    def it_is_one_line_for_argv() -> None:
        assert "\n" not in envoy_config(CLAUDE, "/s").replace("\\n", "")
