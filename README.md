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

# Install to PATH
./bui --install

# Update to latest version
bui --update
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

Use `--bind-cwd` to allow read-write access to your current directory:

```bash
bui --profile untrusted --sandbox deno --bind-cwd -- deno run script.ts
```

### Customizing Profiles

To create a custom profile based on `untrusted`:

1. Run `bui` to open the UI
2. Press `l` to load the `untrusted` profile
3. Modify settings as needed
4. Press `s` and save with a new name (e.g., `my-profile`)

Your custom profile will be saved to `~/.config/bui/profiles/my-profile.json`.

## Sandbox Management

### Installing Binaries

After installing software in a sandbox, use `--install` to create a wrapper script in `~/.local/bin`:

```bash
bui --sandbox deno --install
```

This scans the sandbox for executables and installs a wrapper script:

```
Executables in sandbox 'deno':
  1. .deno/bin/deno

Select binary (number): 1
Installed: /home/user/.local/bin/deno
```

Now you can use `deno` from any directory (no shell rc changes needed):

```bash
cd ~/projects/myapp
deno compile main.ts
```

The wrapper script automatically runs the binary in its sandbox with `--bind-cwd`, allowing it to read and write files in your current directory.

### Listing Sandboxes

List all sandboxes and their installed binaries:

```bash
bui --list-sandboxes
```

Output:

```
Sandboxes:
  deno     (installed: deno)
  node     (installed: node, npm, npx)
  rust     (no binaries installed)
```

### Uninstalling Sandboxes

Remove a sandbox and all its installed binaries:

```bash
bui --sandbox deno --uninstall
```

Output:

```
Removed: /home/user/.local/bin/deno
Removed: /home/user/.local/state/bui/overlays/deno/
```

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
