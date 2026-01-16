"""Tests for build process and built script execution."""

import subprocess
import sys
from pathlib import Path

import pytest

# Get project root (parent of tests/)
PROJECT_ROOT = Path(__file__).parent.parent


class TestBuild:
    """Test that build.py produces a working script."""

    def test_build_produces_executable(self):
        """build.py creates bui script that can execute."""
        # Run build.py
        result = subprocess.run(
            [sys.executable, "build.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"build.py failed: {result.stderr}"

        # Verify bui was created
        bui_path = PROJECT_ROOT / "bui"
        assert bui_path.exists(), "bui script was not created"

    def test_built_script_shows_help(self):
        """Built bui script can execute --help without import errors."""
        # First ensure we have a fresh build
        subprocess.run(
            [sys.executable, "build.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )

        # Run bui --help - this exercises all imports without starting the TUI
        result = subprocess.run(
            ["uv", "run", "./bui", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # --help should exit 0 and not have import errors
        assert "ModuleNotFoundError" not in result.stderr, f"Import error: {result.stderr}"
        assert "ImportError" not in result.stderr, f"Import error: {result.stderr}"
        assert "SyntaxError" not in result.stderr, f"Syntax error: {result.stderr}"
        assert result.returncode == 0, f"bui --help failed: {result.stderr}"

    def test_built_script_exercises_runtime(self):
        """Built script can start TUI without runtime errors.

        This catches deferred import issues that --help wouldn't trigger.
        We run the actual script and check for Python errors in stderr.
        """
        subprocess.run(
            [sys.executable, "build.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )

        # Run the actual built script - it will start the TUI
        # We give it a few seconds to crash or start successfully
        process = subprocess.Popen(
            ["uv", "run", "--with", "textual", "./bui", "--", "true"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        import time
        time.sleep(2)  # Give it time to crash if it's going to

        # Check if process crashed
        poll_result = process.poll()
        if poll_result is not None and poll_result != 0:
            # Process exited with error - get stderr
            _, stderr = process.communicate()
            # Fail with the actual error
            pytest.fail(f"bui crashed with exit code {poll_result}: {stderr}")

        # Process is still running (TUI started) or exited cleanly - kill it
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate()

        # Check stderr for Python errors that might have been logged
        python_errors = ["ModuleNotFoundError", "ImportError", "SyntaxError",
                        "NameError", "IndentationError", "AttributeError"]
        for error in python_errors:
            if error in stderr:
                pytest.fail(f"Python error in stderr: {stderr}")

    def test_built_script_has_version(self):
        """Built script contains version string."""
        bui_path = PROJECT_ROOT / "bui"
        if not bui_path.exists():
            subprocess.run(
                [sys.executable, "build.py"],
                cwd=PROJECT_ROOT,
                capture_output=True,
            )

        content = bui_path.read_text()
        assert "BUI_VERSION" in content, "Version constant not found in built script"


class TestBuiltScriptDefaults:
    """Test that built script has correct default values."""

    def test_etc_default_is_false(self):
        """bind_etc should default to False (unchecked)."""
        bui_path = PROJECT_ROOT / "bui"
        if not bui_path.exists():
            subprocess.run(
                [sys.executable, "build.py"],
                cwd=PROJECT_ROOT,
                capture_output=True,
            )

        content = bui_path.read_text()
        # Find the bind_etc UIField definition
        # It should be: bind_etc = UIField(bool, False, "opt-etc", ...)
        import re
        match = re.search(r'bind_etc\s*=\s*UIField\s*\(\s*bool\s*,\s*(True|False)', content)
        assert match is not None, "bind_etc UIField not found"
        default_value = match.group(1)
        assert default_value == "False", f"bind_etc default should be False, got {default_value}"
