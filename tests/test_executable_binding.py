"""Executable grants must not expose adjacent host files (#119)."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

import cli
from app import BubblewrapTUI
from model import BoundDirectory
from profiles import Profile


@pytest.fixture
def executable_files(tmp_path, monkeypatch):
    home = tmp_path / "fake-home"
    home.mkdir()
    (home / ".ssh").mkdir()
    for name in ("private-marker", ".ssh/dummy-key"):
        (home / name).write_text("DUMMY_SECRET")
    program = home / "test-program"
    program.write_text('''#!/usr/bin/python3
import errno
from pathlib import Path
import sys

program = Path(__file__)
assert program.read_text().startswith("#!/usr/bin/python3")
allowed = sys.argv[1] == "allowed"
for name in ("private-marker", ".ssh/dummy-key"):
    try:
        secret = (program.parent / name).read_text()
    except (FileNotFoundError, PermissionError):
        assert not allowed, name
    else:
        assert allowed, "Unexpected access to " + name
        assert secret == "DUMMY_SECRET"
if not allowed:
    try:
        program.write_text("unexpected overwrite")
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EROFS), exc
    else:
        raise AssertionError("Implicit executable bind must be read-only")
print("SIBLINGS_ALLOWED" if allowed else "SIBLINGS_BLOCKED")
''')
    program.chmod(0o755)
    alias = tmp_path / "program-link"
    alias.symlink_to(program)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("PATH", str(home) + os.pathsep + os.environ.get("PATH", ""))
    return program, alias


@pytest.fixture(params=["absolute", "relative", "path", "symlink"])
def executable_command(request, executable_files):
    program, alias = executable_files
    return {
        "absolute": str(program),
        "relative": os.path.relpath(program),
        "path": program.name,
        "symlink": str(alias),
    }[request.param]


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    # Exercise parsing/loading/launch while keeping real installation state intact.
    monkeypatch.setattr(cli, "cleanup_orphaned_sandboxes", lambda: None)
    monkeypatch.setattr(cli, "check_for_updates", lambda version: None)
    monkeypatch.setattr("virtual_files.tempfile.tempdir", str(tmp_path))


def run_cli(profile_path, command, monkeypatch, extra=()):
    monkeypatch.setattr(sys, "argv", [
        "bui", "--profile", str(profile_path), *extra, "--", *command,
    ])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


@pytest.mark.parametrize("entrypoint", ["cli", "tui"])
def test_automatic_bind_grants_only_executable(
    untrusted_config, tmp_path, monkeypatch, executable_files, executable_command,
    isolated_cli, entrypoint,
):
    program, alias = executable_files
    command = [executable_command, "blocked"]
    if entrypoint == "tui":
        config = BubblewrapTUI(command).config
    else:
        untrusted_config.overlays = []
        profile = Profile(tmp_path / "profile.json")
        profile.save(untrusted_config)
        captured = []

        def capture(config, *args):
            captured.append(config)
            raise SystemExit(0)

        monkeypatch.setattr(cli, "execute_sandbox", capture)
        assert run_cli(profile.path, command, monkeypatch) == 0
        config = captured[0]

    assert config.command == [str(program), "blocked"]
    binds = {entry.path: entry for entry in config.bound_dirs}
    assert program in binds
    assert binds[program].readonly
    assert program.parent not in binds
    assert alias.parent not in binds
    assert Path.cwd() not in binds

    # File binds must survive the existing profile format without widening access.
    saved = Profile(tmp_path / "saved.json")
    saved.save(config)
    restored, warnings = saved.load(config.command)
    assert warnings == []
    assert restored.bound_dirs == config.bound_dirs


def test_tui_started_in_executable_directory_does_not_grant_cwd(executable_files, monkeypatch):
    program, _ = executable_files
    monkeypatch.chdir(program.parent)
    config = BubblewrapTUI(["./test-program"]).config
    assert any(entry.path == program for entry in config.bound_dirs)
    assert all(entry.path != program.parent for entry in config.bound_dirs)


@pytest.mark.asyncio
async def test_tui_does_not_select_an_unmounted_working_directory(executable_files, monkeypatch):
    from textual.widgets import Input

    program, _ = executable_files
    monkeypatch.chdir(program.parent)
    app = BubblewrapTUI(["./test-program", "blocked"])
    async with app.run_test() as pilot:
        await pilot.pause()
        app._sync_config_from_ui()
        assert app.config.process.chdir == ""
        assert "--chdir" not in app.config.build_command()
        assert all(entry.path != program.parent for entry in app.config.bound_dirs)

        # An explicit sandbox working directory is still honored.
        app.query_one("#opt-chdir", Input).value = "/tmp"
        app._sync_config_from_ui()
        assert app.config.process.chdir == "/tmp"


@pytest.mark.skipif(
    os.environ.get("BUI_TEST_NETWORK") != "1",
    reason="Set BUI_TEST_NETWORK=1 to exercise real rootless bubblewrap isolation",
)
@pytest.mark.parametrize("grant", ["none", "profile", "bind", "cwd"])
def test_executable_runs_without_implicit_sibling_access(
    untrusted_config, tmp_path, monkeypatch, executable_files, executable_command,
    isolated_cli, grant,
):
    program, _ = executable_files
    config = untrusted_config
    config.overlays = []
    config.network.share_net = False
    config.network.network_mode = "off"
    config.network.bind_resolv_conf = False
    config.network.bind_ssl_certs = False
    extra = []
    if grant == "profile":
        config.bound_dirs.append(BoundDirectory(program.parent))
    elif grant == "bind":
        extra = ["--bind", str(program.parent)]
    elif grant == "cwd":
        # Resolve relative invocation before changing cwd for the explicit grant.
        if "/" in executable_command:
            executable_command = str(Path(executable_command).absolute())
        monkeypatch.chdir(program.parent)
        extra = ["--bind-cwd"]

    profile = Profile(tmp_path / "profile.json")
    profile.save(config)
    results = []

    def run_without_terminal(cmd, seccomp_fd=None):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                pass_fds=() if seccomp_fd is None else (seccomp_fd,),
            )
            results.append(result)
            return result.returncode
        finally:
            if seccomp_fd is not None:
                os.close(seccomp_fd)

    monkeypatch.setattr("command_execution._run_with_pty", run_without_terminal)
    expected = "blocked" if grant == "none" else "allowed"
    code = run_cli(profile.path, [executable_command, expected], monkeypatch, extra)
    result = results[-1]
    assert code == 0, result.stdout + result.stderr
    assert ("SIBLINGS_BLOCKED" if grant == "none" else "SIBLINGS_ALLOWED") in result.stdout
