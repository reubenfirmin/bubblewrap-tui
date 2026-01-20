# bui - Bubblewrap TUI

A terminal user interface for configuring and launching [bubblewrap](https://github.com/containers/bubblewrap) sandboxes.

Instead of memorizing dozens of `bwrap` flags, visually configure your sandbox and see the generated command before execution.

## Status

- Beta quality, lightly tested. That said it doesn't do anything except generate (and run, on demand) a bwrap command, so is mostly harmless.
- PRs and bug reports welcome. Feature requests will be considered.

## Requirements

- [uv](https://github.com/astral-sh/uv) - see [installation docs](https://docs.astral.sh/uv/getting-started/installation/)
- [bubblewrap](https://github.com/containers/bubblewrap)

## Installation

```bash
curl -LO https://github.com/reubenfirmin/bubblewrap-tui/releases/latest/download/bui
chmod +x bui
./bui --install
```

Update to latest: `bui --update`

## Quick Start

Launch the TUI to configure a sandbox interactively:

```bash
bui -- /bin/bash
```

The TUI lets you:
- Toggle filesystem access (read-only system paths, /tmp, /etc, etc.)
- Add bound directories (read-only or read-write)
- Configure overlays for persistent changes
- Set environment variables
- Enable/disable network access
- Save configurations as reusable profiles

Press `x` to execute with your configuration, or `q` to quit.

## Profiles

Profiles are saved sandbox configurations that can be reused from the command line.

### The `untrusted` Profile

Running `bui --install` creates a built-in `untrusted` profile designed for running untrusted code safely:

- Read-only system paths (`/usr`, `/bin`, `/lib`, etc.)
- Home directory via overlay (changes are isolated, not written to your real home)
- Network access enabled (for downloads)
- Strong isolation (new session, PID namespace, dropped capabilities)

### Custom Profiles

Create your own profiles:

1. Run `bui -- /bin/bash`
2. Configure settings in the TUI
3. Press `s` to save with a name (e.g., `my-profile`)

Profiles are stored in `~/.config/bui/profiles/`.

## Managed Sandboxes

For applications you want to install and run repeatedly in isolation, bui provides managed sandboxes. This is useful for:

- Running `curl | bash` install scripts safely
- Isolating development tools from your system
- Running AI coding assistants with restricted access

### Example: Installing Deno

Install Deno in an isolated sandbox:

```bash
# Run the install script in a sandbox named "deno"
bui --profile untrusted --sandbox deno -- 'curl -fsSL https://deno.land/install.sh | sh'
```

This runs the install script with:
- Read-only access to system paths
- Home directory changes captured in an overlay (`~/.local/state/bui/overlays/deno/`)
- Network access for downloads
- Full isolation from your real home directory

After installation, create a wrapper script so you can use `deno` normally:

```bash
bui --sandbox deno --install
```

```
Executables in sandbox 'deno':
  1. .deno/bin/deno

Select binary (number): 1
Installed: /home/user/.local/bin/deno
```

Now use Deno from any directory - `--bind-cwd` is automatic:

```bash
cd ~/projects/myapp
deno run server.ts
deno compile main.ts
```

### Example: Running Claude Code in a Sandbox

Run Claude Code with restricted filesystem access:

```bash
# Install Claude Code in a sandbox
bui --profile untrusted --sandbox claude -- 'npm install -g @anthropic-ai/claude-code'

# Create wrapper script
bui --sandbox claude --install
# Select: claude

# Use it - your current directory is accessible read-write
cd ~/projects/myapp
claude
```

Claude Code runs isolated from your system, but can read and write files in whatever directory you run it from.

### Managing Sandboxes

List installed sandboxes:

```bash
bui --list-sandboxes
```

```
Sandboxes:
  deno
    profile: untrusted
    scripts: deno
  claude
    profile: untrusted
    scripts: claude
```

List overlay directories (including orphaned ones):

```bash
bui --list-overlays
```

```
Overlays:
  /home/user/.local/state/bui/overlays/deno/
    files: 127
    To remove: bui --sandbox deno --uninstall
  /home/user/.local/state/bui/overlays/abc123/
    files: 8
    No sandbox installed (safe to delete)
```

Uninstall a sandbox:

```bash
bui --sandbox deno --uninstall
```

```
Removed: /home/user/.local/bin/deno
Removed: /home/user/.local/state/bui/overlays/deno/
```

## Development

```bash
# Run tests
uv run --with pytest --with pytest-cov --with pytest-asyncio --with textual pytest tests/ -v

# With coverage
uv run --with pytest --with pytest-cov --with pytest-asyncio --with textual pytest tests/ --cov=src --cov-report=term-missing
```

## License

MIT
