# bui - Bubblewrap TUI

A terminal user interface for configuring and launching [bubblewrap](https://github.com/containers/bubblewrap) sandboxes.

Instead of memorizing dozens of `bwrap` flags, visually configure your sandbox and see the generated command before execution.

## Status

- This is both beta quality and lightly tested. That said it doesn't do anything except generate (and run, on demand) a bwrap command, so is mostly harmless. 
- PRs and bug reports are welcomed. Feature requests will be considered. :) 

## Requirements

- [uv](https://github.com/astral-sh/uv)
- [bubblewrap](https://github.com/containers/bubblewrap)

## Installation

### Install uv

See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for your platform.

### Get bui

```bash
# Download from releases
curl -LO https://github.com/reubenfirmin/bubblewrap-tui/releases/latest/download/bui
chmod +x bui

# Optionally install to PATH
./bui --install
```

## Usage

```bash
# Basic usage - sandbox a shell
bui -- /bin/bash

# Sandbox a specific command
bui -- python script.py

# Shell commands (pipes and redirects auto-handled)
bui -- "curl foo.sh | bash"
```

## Profiles

### The `untrusted` Profile

Running `bui --install` creates a default `untrusted` profile at `~/.config/bui/profiles/untrusted.json`. This profile is designed for running untrusted code (e.g., `curl | bash` install scripts):

- Read-only access to system paths (`/usr`, `/bin`, `/lib`, etc.)
- Home directory via overlay (changes persist to `~/.local/state/bui/overlays/`)
- Network access enabled
- Strong isolation (new session, PID namespace, dropped capabilities)

Use it with `--profile untrusted`:

```bash
bui --profile untrusted -- "curl -fsSL https://example.com/install.sh | sh"
```

Add `--sandbox <name>` to isolate installations from each other:

```bash
bui --profile untrusted --sandbox deno -- "curl -fsSL https://deno.land/install.sh | sh"
```

### Customizing Profiles

To create a custom profile based on `untrusted`:

1. Run `bui` to open the UI
2. Press `l` to load the `untrusted` profile
3. Modify settings as needed
4. Press `s` and save with a new name (e.g., `my-profile`)

Your custom profile will be saved to `~/.config/bui/profiles/my-profile.json`.

## Development

### Running Tests

```bash
uv run --with pytest --with pytest-cov --with pytest-asyncio --with textual pytest tests/ -v
```

With coverage report:

```bash
uv run --with pytest --with pytest-cov --with pytest-asyncio --with textual pytest tests/ --cov=src --cov-report=term-missing
```

## License

MIT
