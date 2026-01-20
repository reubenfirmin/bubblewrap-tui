# bui - Bubblewrap TUI

A terminal user interface for configuring and launching [bubblewrap](https://github.com/containers/bubblewrap) sandboxes.

Instead of memorizing dozens of `bwrap` flags, visually configure your sandbox and see the generated command before execution.

## Status

- Beta quality, moderately tested. That said it doesn't do anything except generate (and run, on demand) a bwrap command, so is mostly harmless. Do your own diligence before trusting the security of critical data to it, and also review bubblewrap CVEs / known issues.
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

Profiles are saved sandbox configurations. Once you have a profile, you can skip the TUI and run commands directly:

```bash
bui --profile <name> -- <command>
```

This is useful for:
- Scripting and automation
- Running the same sandbox configuration repeatedly
- Sharing configurations with others

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

AI coding assistants like Claude Code can execute arbitrary shell commands and modify files. Running them in a sandbox provides defense in depth - even if the AI makes a mistake or is manipulated, it can only affect files you explicitly allow.

**What the sandbox provides:**
- Claude cannot read `~/.ssh`, `~/.aws`, `~/.gnupg`, browser data, or other sensitive dotfiles
- Claude cannot modify system files or install packages globally on your system
- Each project directory is explicitly granted access via `--bind-cwd`
- All of Claude's installed files (npm packages, config) live in an isolated overlay

**The tradeoff:** You need `--bind` and `--bind-env` flags to expose tools and configure the environment, rather than creating a custom profile. This is intentional - the generic `untrusted` profile works for many use cases without per-tool maintenance.

#### Installation

The `untrusted` profile only exposes system paths (`/usr`, `/bin`, `/lib`). If npm/node are installed in your home directory (e.g., via nvm), bind them explicitly:

```bash
# Install Claude Code in a sandbox
# --bind: expose the directory containing npm (needed for installation)
# --bind-env: set NPM_CONFIG_PREFIX so npm installs to the sandbox home, not /usr
bui --profile untrusted --sandbox claude \
    --bind $(dirname $(which npm)) \
    --bind-env 'NPM_CONFIG_PREFIX=/home/sandbox/.npm-global' \
    -- npm install -g @anthropic-ai/claude-code
```

Create a wrapper script so you can run `claude` from anywhere:

```bash
bui --sandbox claude --install
# Select: claude
```

#### Usage

```bash
cd ~/projects/myapp
claude
```

The wrapper script automatically:
- Runs Claude in the sandbox with your saved profile
- Binds your current directory read-write (`--bind-cwd`)
- Passes through the bind paths and environment from installation

Because the wrapper uses `--bind-cwd`, Claude can read and write files in your current directory. It cannot access other directories, your home directory, or sensitive dotfiles.

#### Terminal colors

If the terminal looks basic (no colors), add TERM to your sandbox:

```bash
# One-time fix
bui --sandbox claude --bind-env "TERM=$TERM" -- claude

# Or regenerate the default profile which now includes TERM
bui --install
```

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
