import re
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from botbox.Botbox import Botbox

RELAY_DIR = Path(__file__).with_name("relay")


class DockerException(Exception):
    """Stands in for python_on_whales' DockerException."""


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.Botbox.DockerException", DockerException):
        yield


AGENT_DOCKERFILE = Path("/agents/an-agent.Dockerfile")


@pytest.fixture
def agent() -> Mock:
    return Mock(
        image="an-agent:latest",
        dockerfile=AGENT_DOCKERFILE,
        home="/home/agent",
        transcripts="sessions/**/*.jsonl",
        allow=("api.example",),
    )


@pytest.fixture(autouse=True)
def docker() -> Iterator[MagicMock]:
    with patch("botbox.Botbox.docker", autospec=True) as m:
        yield m


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    return tmp_path / "consumer" / "Dockerfile"


def describe_botbox() -> None:
    def it_keeps_the_agent(agent: Mock) -> None:
        assert Botbox(agent).agent is agent

    def it_takes_its_options_by_keyword_only(agent: Mock, layer: Path) -> None:
        with pytest.raises(TypeError):
            Botbox(agent, layer)  # type: ignore[call-arg]

    def it_has_no_dockerfile_by_default(agent: Mock) -> None:
        assert Botbox(agent).dockerfile is None

    def it_holds_the_dockerfile_as_an_absolute_path(agent: Mock, layer: Path) -> None:
        assert Botbox(agent, dockerfile=str(layer)).dockerfile == layer

    def it_allows_nothing_extra_by_default(agent: Mock) -> None:
        assert Botbox(agent).allow == ()

    def it_holds_the_extra_hosts_as_a_tuple(agent: Mock) -> None:
        assert Botbox(agent, allow=["registry.npmjs.org"]).allow == ("registry.npmjs.org",)

    def it_refuses_a_bare_string_that_would_split_into_characters(agent: Mock) -> None:
        with pytest.raises(TypeError, match=r"allow=\('github\.com',\)"):
            Botbox(agent, allow="github.com")


@pytest.fixture
def steps(docker: MagicMock) -> Iterator[list[str]]:
    """Each lock taken and released, and each build, in order."""
    steps: list[str] = []

    @contextmanager
    def lock(tag: str) -> Iterator[None]:
        steps.append(f"lock {tag}")
        yield
        steps.append(f"unlock {tag}")

    docker.build.side_effect = lambda *_args, tags, **_options: steps.append(f"build {tags}")
    with patch("botbox.Botbox.build_lock", lock):
        yield steps


def describe_build() -> None:
    def describe_without_a_dockerfile() -> None:
        def it_returns_the_agents_tag(agent: Mock) -> None:
            assert Botbox(agent).build() == "an-agent:latest"

        def it_builds_the_agent_dockerfile_quietly_in_its_directory(
            agent: Mock, docker: MagicMock
        ) -> None:
            Botbox(agent).build()
            assert docker.build.call_args_list == [
                call(
                    Path("/agents"),
                    tags="an-agent:latest",
                    file=AGENT_DOCKERFILE,
                    build_contexts={"botbox": RELAY_DIR},
                    progress=False,
                )
            ]

    def describe_with_a_dockerfile() -> None:
        def it_tags_the_layer_after_the_agent_image_and_the_dockerfile(
            agent: Mock, layer: Path
        ) -> None:
            assert re.fullmatch(
                r"an-agent-[0-9a-f]{12}:latest", Botbox(agent, dockerfile=layer).build()
            )

        def it_builds_the_layer_quietly_in_its_directory_after_the_agent_image(
            agent: Mock, docker: MagicMock, layer: Path
        ) -> None:
            tag = Botbox(agent, dockerfile=layer).build()
            assert docker.build.call_args_list == [
                call(
                    Path("/agents"),
                    tags="an-agent:latest",
                    file=AGENT_DOCKERFILE,
                    build_contexts={"botbox": RELAY_DIR},
                    progress=False,
                ),
                call(layer.parent, tags=tag, file=layer, progress=False),
            ]

    def it_holds_each_tags_lock_only_while_building_it(
        agent: Mock, layer: Path, steps: list[str]
    ) -> None:
        tag = Botbox(agent, dockerfile=layer).build()
        assert steps == [
            "lock an-agent:latest",
            "build an-agent:latest",
            "unlock an-agent:latest",
            f"lock {tag}",
            f"build {tag}",
            f"unlock {tag}",
        ]


@pytest.fixture
def jail() -> Mock:
    return Mock(
        proxy="a-proxy",
        sockets=Path("/scratch/sockets"),
        envs={"HTTPS_PROXY": "http://127.0.0.1:41893"},
        log="a log",
    )


@pytest.fixture
def lockdown(jail: Mock) -> Iterator[MagicMock]:
    with patch("botbox.Botbox.lockdown", autospec=True) as m:
        m.side_effect = lambda _allow, _scratch: nullcontext(jail)
        yield m


@pytest.fixture
def bind_mounts() -> Iterator[MagicMock]:
    with patch("botbox.Botbox.bind_mounts", autospec=True) as m:
        m.return_value = [("/host/work", "/work", "rw")]
        yield m


@pytest.fixture
def collect() -> Iterator[MagicMock]:
    with patch("botbox.Botbox.collect", autospec=True) as m:
        m.return_value = ("out", "err", 7)
        yield m


@pytest.fixture
def run(
    agent: Mock,
    docker: MagicMock,  # noqa: ARG001
    lockdown: MagicMock,  # noqa: ARG001
    bind_mounts: MagicMock,  # noqa: ARG001
    collect: MagicMock,  # noqa: ARG001
) -> Botbox:
    return Botbox(agent, allow=["extra.example"])


def home_in(argv: list[str]) -> Path:
    return Path(argv[argv.index("--volume") + 1].split(":")[0])


def name_in(argv: list[str]) -> str:
    return argv[argv.index("--name") + 1]


def locked_down(home: Path, name: str) -> list[str]:
    """The flags every agent container runs with, in `Botbox`'s order."""
    return [
        "--rm",
        "--name",
        name,
        "--env",
        "HTTPS_PROXY=http://127.0.0.1:41893",
        "--volume",
        f"{home}:/home/agent:rw",
        "--volume",
        "/scratch/sockets:/run/botbox:ro",
        "--volume",
        "/host/work:/work:rw",
        "--workdir",
        "/home/agent",
        "--network",
        "none",
        "--pid",
        "container:a-proxy",
        "--user",
        "user",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
    ]


def describe_run() -> None:
    def it_takes_mounts_and_workdir_by_keyword_only(run: Botbox) -> None:
        with pytest.raises(TypeError):
            run.run("true", [])  # type: ignore[call-arg]

    def it_checks_the_mounts_and_workdir_against_the_agents_home(
        run: Botbox, bind_mounts: MagicMock
    ) -> None:
        mounts = [(Path("/host/work"), "/work", "rw")]
        run.run("true", mounts=mounts, workdir="/work")  # type: ignore[arg-type]
        bind_mounts.assert_called_once_with(mounts, workdir="/work", home="/home/agent")

    def it_builds_nothing_when_the_check_fails(
        run: Botbox, bind_mounts: MagicMock, docker: MagicMock, lockdown: MagicMock
    ) -> None:
        bind_mounts.side_effect = ValueError("workdir")
        with pytest.raises(ValueError, match="workdir"):
            run.run("true")
        docker.build.assert_not_called()
        lockdown.assert_not_called()

    def it_runs_the_built_image_locked_down_in_one_docker_run(
        run: Botbox, collect: MagicMock
    ) -> None:
        run.run("echo hi")
        [argv] = collect.call_args.args
        assert re.fullmatch(r"botbox-agent-[0-9a-f]{12}", name_in(argv))
        assert argv == [
            "docker",
            "run",
            *locked_down(home_in(argv), name_in(argv)),
            "an-agent:latest",
            "/usr/local/bin/botbox-relay",
            "sh",
            "-c",
            "echo hi",
        ]

    def it_builds_before_it_runs(run: Botbox, docker: MagicMock, collect: MagicMock) -> None:
        collect.side_effect = lambda _argv: (docker.build.assert_called(), ("", "", 0))[1]
        run.run("true")

    def it_starts_in_the_workdir_when_given(run: Botbox, collect: MagicMock) -> None:
        run.run("true", workdir=Path("/work/pkg"))
        [argv] = collect.call_args.args
        assert argv[argv.index("--workdir") + 1] == "/work/pkg"

    def it_locks_down_with_the_agents_hosts_and_the_callers(
        run: Botbox, lockdown: MagicMock, collect: MagicMock
    ) -> None:
        run.run("true")
        [(allow, scratch)] = [c.args for c in lockdown.call_args_list]
        assert allow == ("api.example", "extra.example")
        assert home_in(collect.call_args.args[0]) == scratch / "home"

    def it_stages_the_credentials_into_the_mounted_home(
        run: Botbox, agent: Mock, collect: MagicMock
    ) -> None:
        run.run("true")
        agent.stage_auth.assert_called_once_with(home_in(collect.call_args.args[0]))

    def it_raises_before_locking_down_when_staging_fails(
        run: Botbox, agent: Mock, lockdown: MagicMock
    ) -> None:
        agent.stage_auth.side_effect = FileNotFoundError(".credentials.json")
        with pytest.raises(FileNotFoundError):
            run.run("true")
        lockdown.assert_not_called()

    def it_returns_the_output_exit_code_and_proxy_log(run: Botbox) -> None:
        r = run.run("true")
        assert (r.stdout, r.stderr, r.exit_code, r.transcript, r.proxy) == (
            "out",
            "err",
            7,
            {},
            "a log",
        )

    def it_reads_the_transcript_files_relative_to_the_home(run: Botbox, collect: MagicMock) -> None:
        def container_writes(argv: list[str]) -> tuple[str, str, int]:
            home = home_in(argv)
            (home / "sessions" / "a" / "b.jsonl").parent.mkdir(parents=True)
            (home / "sessions" / "a" / "b.jsonl").write_text("b")
            (home / "sessions" / "c.jsonl").write_text("c")
            (home / "sessions" / "dir.jsonl").mkdir()
            (home / "sessions" / "notes.txt").write_text("n")
            (home / "other.jsonl").write_text("o")
            return "", "", 0

        collect.side_effect = container_writes
        assert run.run("true").transcript == {"sessions/a/b.jsonl": "b", "sessions/c.jsonl": "c"}

    def it_returns_the_image_it_ran(run: Botbox) -> None:
        assert run.run("true").image == "an-agent:latest"

    def it_returns_the_layered_image_when_given_a_dockerfile(
        run: Botbox,  # noqa: ARG001
        agent: Mock,
        layer: Path,
    ) -> None:
        box = Botbox(agent, dockerfile=layer)
        assert box.run("true").image == box.build()

    def it_leaves_the_container_to_remove_itself(run: Botbox, docker: MagicMock) -> None:
        run.run("true")
        docker.container.remove.assert_not_called()

    def it_removes_the_container_by_name_when_interrupted(
        run: Botbox, docker: MagicMock, collect: MagicMock
    ) -> None:
        collect.side_effect = KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt), run:
            run.run("true")
        [argv] = collect.call_args.args
        assert docker.container.remove.call_args_list == [call(name_in(argv), force=True)]
        assert not home_in(argv).parent.exists()

    def it_keeps_the_error_when_the_client_cannot_start_and_removal_fails(
        run: Botbox, docker: MagicMock, collect: MagicMock
    ) -> None:
        collect.side_effect = FileNotFoundError("docker")
        docker.container.remove.side_effect = DockerException("daemon gone")
        with pytest.raises(FileNotFoundError):
            run.run("true")

    def it_deletes_the_temporary_directory(run: Botbox, collect: MagicMock) -> None:
        run.run("true")
        home = home_in(collect.call_args.args[0])
        assert home.parent.name.startswith("botbox-")
        assert not home.parent.exists()


def describe_with() -> None:
    def it_is_the_box(run: Botbox) -> None:
        with run as box:
            assert box is run

    def it_removes_nothing_on_exit(run: Botbox, docker: MagicMock) -> None:
        with run:
            run.run("true")
            run.run("true")
        docker.container.remove.assert_not_called()

    def it_leaves_the_results_readable(run: Botbox) -> None:
        with run:
            result = run.run("true")
        assert (result.stdout, result.stderr, result.proxy) == ("out", "err", "a log")

    def describe_sigterm() -> None:
        @pytest.fixture(autouse=True)
        def threads() -> Iterator[MagicMock]:
            with patch("botbox.Botbox.threading", autospec=True) as m:
                m.current_thread.return_value = m.main_thread.return_value
                yield m

        @pytest.fixture(autouse=True)
        def signals() -> Iterator[MagicMock]:
            with patch("botbox.Botbox.signal", autospec=True) as m:
                m.getsignal.return_value = m.SIG_DFL
                yield m

        def it_makes_sigterm_unwind_inside_the_block(run: Botbox, signals: MagicMock) -> None:
            with run:
                [(signum, handler)] = [c.args for c in signals.signal.call_args_list]
                assert signum == signals.SIGTERM
                with pytest.raises(SystemExit) as raised:
                    handler(15, None)
            assert raised.value.code == 143

        def it_restores_the_default_handler_on_exit(run: Botbox, signals: MagicMock) -> None:
            with run:
                pass
            assert signals.signal.call_args == call(signals.SIGTERM, signals.SIG_DFL)

        def it_leaves_a_programs_own_handler_alone(run: Botbox, signals: MagicMock) -> None:
            signals.getsignal.return_value = Mock()
            with run:
                pass
            signals.signal.assert_not_called()

        def it_restores_only_what_it_installed(run: Botbox, signals: MagicMock) -> None:
            with run:
                pass
            signals.getsignal.return_value = Mock()
            signals.signal.reset_mock()
            with run:
                pass
            signals.signal.assert_not_called()

        def it_does_nothing_off_the_main_thread(
            run: Botbox, threads: MagicMock, signals: MagicMock
        ) -> None:
            threads.current_thread.return_value = Mock()
            with run:
                pass
            signals.signal.assert_not_called()


@pytest.fixture
def subprocess() -> Iterator[MagicMock]:
    with patch("botbox.Botbox.subprocess", autospec=True) as m:
        yield m


@pytest.fixture
def popen(subprocess: MagicMock) -> MagicMock:
    subprocess.Popen.return_value = Mock(stdin=Mock(), stdout=iter(()), stderr=iter(()))
    subprocess.Popen.return_value.wait.return_value = 0
    popen: MagicMock = subprocess.Popen
    return popen


@pytest.fixture
def session_box(
    agent: Mock,
    docker: MagicMock,  # noqa: ARG001
    lockdown: MagicMock,  # noqa: ARG001
    bind_mounts: MagicMock,  # noqa: ARG001
    popen: MagicMock,  # noqa: ARG001
) -> Botbox:
    # Set outright: the SessionAgent check looks attributes up statically, past Mock's magic.
    for method in ("stage_auth", "command", "session_command", "encode", "turn_ended"):
        setattr(agent, method, Mock())
    agent.session_command.return_value = "an-agent --stream"
    return Botbox(agent, allow=["extra.example"])


def session_home_of(popen: MagicMock) -> Path:
    return home_in(popen.call_args.args[0])


def session_name_of(popen: MagicMock) -> str:
    return name_in(popen.call_args.args[0])


def describe_session() -> None:
    def it_takes_mounts_and_workdir_by_keyword_only(session_box: Botbox) -> None:
        with pytest.raises(TypeError):
            session_box.session([])  # type: ignore[call-arg]

    def it_refuses_an_agent_with_no_session_mode(agent: Mock, docker: MagicMock) -> None:
        with pytest.raises(TypeError, match="no session mode"):
            Botbox(agent).session()
        docker.build.assert_not_called()

    def it_asks_for_the_session_command_before_building(
        session_box: Botbox, agent: Mock, docker: MagicMock
    ) -> None:
        agent.session_command.side_effect = NotImplementedError("no")
        with pytest.raises(NotImplementedError):
            session_box.session()
        docker.build.assert_not_called()
        agent.stage_auth.assert_not_called()

    def it_checks_the_mounts_and_workdir_against_the_agents_home(
        session_box: Botbox, bind_mounts: MagicMock
    ) -> None:
        mounts = [(Path("/host/work"), "/work", "rw")]
        session_box.session(mounts=mounts, workdir="/work")  # type: ignore[arg-type]
        bind_mounts.assert_called_once_with(mounts, workdir="/work", home="/home/agent")

    def it_runs_the_container_locked_down_and_attached_with_pipes(
        session_box: Botbox, popen: MagicMock, subprocess: MagicMock
    ) -> None:
        session_box.session()
        name = session_name_of(popen)
        assert re.fullmatch(r"botbox-agent-[0-9a-f]{12}", name)
        assert popen.call_args == call(
            [
                "docker",
                "run",
                "--interactive",
                *locked_down(session_home_of(popen), name),
                "an-agent:latest",
                "/usr/local/bin/botbox-relay",
                "sh",
                "-c",
                "an-agent --stream",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def it_starts_in_the_workdir_when_given(session_box: Botbox, popen: MagicMock) -> None:
        session_box.session(workdir="/work")
        [argv] = popen.call_args.args
        assert argv[argv.index("--workdir") + 1] == "/work"

    def it_locks_down_with_the_agents_hosts_and_the_callers(
        session_box: Botbox, lockdown: MagicMock
    ) -> None:
        session_box.session()
        assert lockdown.call_args.args[0] == ("api.example", "extra.example")

    def it_stages_the_credentials_into_the_mounted_home(
        session_box: Botbox, agent: Mock, popen: MagicMock
    ) -> None:
        session_box.session()
        agent.stage_auth.assert_called_once_with(session_home_of(popen))

    def it_returns_a_session_on_the_image(session_box: Botbox) -> None:
        assert session_box.session().close().image == "an-agent:latest"

    def it_returns_the_proxy_log_on_close(session_box: Botbox) -> None:
        assert session_box.session().close().proxy == "a log"

    def it_reads_the_transcript_before_deleting_the_home(
        session_box: Botbox, agent: Mock, popen: MagicMock
    ) -> None:
        agent.stage_auth.side_effect = lambda home: (
            (home / "sessions" / "s").mkdir(parents=True),
            (home / "sessions" / "s" / "t.jsonl").write_text("turn"),
        )
        session = session_box.session()
        home = session_home_of(popen)
        assert session.close().transcript == {"sessions/s/t.jsonl": "turn"}
        assert not home.exists()

    def it_keeps_the_home_while_the_session_is_open(session_box: Botbox, popen: MagicMock) -> None:
        session = session_box.session()
        assert session_home_of(popen).is_dir()
        session.close()

    def it_leaves_the_container_to_remove_itself(session_box: Botbox, docker: MagicMock) -> None:
        with session_box:
            session_box.session().close()
        docker.container.remove.assert_not_called()

    def it_tears_down_when_the_client_cannot_start(
        session_box: Botbox, docker: MagicMock, popen: MagicMock
    ) -> None:
        popen.side_effect = OSError("no docker")
        with pytest.raises(OSError, match="no docker"):
            session_box.session()
        docker.container.remove.assert_called_once_with(session_name_of(popen), force=True)
        assert not session_home_of(popen).exists()

    def it_keeps_the_attach_error_when_removal_also_fails(
        session_box: Botbox, docker: MagicMock, popen: MagicMock
    ) -> None:
        popen.side_effect = OSError("no docker")
        docker.container.remove.side_effect = DockerException("daemon gone")
        with pytest.raises(OSError, match="no docker"):
            session_box.session()

    def it_removes_nothing_when_creation_never_started(
        session_box: Botbox, docker: MagicMock, lockdown: MagicMock
    ) -> None:
        lockdown.side_effect = RuntimeError("proxy did not start")
        with pytest.raises(RuntimeError):
            session_box.session()
        docker.container.remove.assert_not_called()

    def it_raises_before_running_a_container_when_staging_fails(
        session_box: Botbox, agent: Mock, popen: MagicMock, lockdown: MagicMock
    ) -> None:
        agent.stage_auth.side_effect = FileNotFoundError("credentials")
        with pytest.raises(FileNotFoundError):
            session_box.session()
        lockdown.assert_not_called()
        popen.assert_not_called()
