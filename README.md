# bui - Bubblewrap TUI

A terminal user interface for configuring and launching [bubblewrap](https://github.com/containers/bubblewrap) sandboxes.

Instead of memorizing dozens of `bwrap` flags, visually configure your sandbox and see the generated command before execution.

## Contents

- [Status](#status)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Profiles](#profiles)
- [Managed Sandboxes](#managed-sandboxes)
  - [Safe curl | bash - Installing Deno](#safe-curl--bash---installing-deno)
  - [Constraining Agents - Sandboxing Claude Code](#constraining-agents---sandboxing-claude-code)
- [Network Filtering](#network-filtering)
  - [Why pasta?](#why-pasta)
  - [How filtering works](#how-filtering-works)
  - [Hostname resolution](#hostname-resolution)
  - [Audit mode](#audit-mode)
  - [Requirements](#requirements-1)
- [Development](#development)
- [License](#license)

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

### Compatibility
- Intended to work on all modern Linux distros. Please file tickets with any issues
- Will not work on OSX, which doesn't have Bubblewrap or equivalents (your best options would be something like Sandbox.app or Docker Desktop)

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

Press `Enter` to execute or `Esc` to quit.

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

- Isolated home directory (your real home is not accessible)
- Read-only system paths (`/usr`, `/bin`, `/lib`, etc.)
- Network access enabled (for downloads)
- Strong isolation (new session, PID namespace, dropped capabilities)

### Custom Profiles

Create your own profiles:

1. Run `bui -- /bin/bash`
2. Configure settings in the TUI
3. Click "Save" to save with a name (e.g., `my-profile`)

Profiles are stored in `~/.config/bui/profiles/`.

## Managed Sandboxes

For applications you want to install and run repeatedly in isolation, bui provides managed sandboxes. This is useful for:

- Running `curl | bash` install scripts safely
- Isolating development tools from your system
- Running AI coding assistants with restricted access

### Safe curl | bash - Installing Deno

Install Deno in an isolated sandbox:

```bash
# Run the install script in a sandbox named "deno"
bui --profile untrusted --sandbox deno -- 'curl -fsSL https://deno.land/install.sh | sh'
```

This runs the install script with:
- Isolated home directory (`~/.local/state/bui/overlays/deno/`) - your real home is not accessible
- Read-only access to system paths
- Network access for downloads

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

### Constraining Agents - Sandboxing Claude Code

AI coding assistants like Claude Code can execute arbitrary shell commands and modify files. Running them in a sandbox provides defense in depth - even if the AI makes a mistake or is manipulated, it can only affect files you explicitly allow.

**What the sandbox provides:**
- Claude cannot read `~/.ssh`, `~/.aws`, `~/.gnupg`, browser data, or other sensitive dotfiles
- Claude cannot modify system files or install packages globally on your system
- Each project directory is explicitly granted access via `--bind-cwd`
- All of Claude's installed files (npm packages, config) live in an isolated overlay

**Why the complex command?** We could create a custom profile in the TUI and use `--profile my-claude-profile`, but here we're reusing the generic `untrusted` profile and layering on a few flags. This is one-time setup - once we run `--install`, we get a permanent wrapper script that handles all of this.

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
    bind: /home/user/.nvm/versions/node/v20.0.0/bin
    bind-env: NPM_CONFIG_PREFIX=/home/sandbox/.npm-global
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

### Tips

**Terminal colors**: If the terminal looks basic (no colors), pass through TERM:

```bash
bui --sandbox myapp --bind-env "TERM=$TERM" -- myapp
```

## Network Filtering

Network filtering uses [pasta](https://passt.top/) (part of passt) to create an isolated network namespace, then applies iptables rules inside that namespace.

### Why pasta?

Creating a network namespace normally requires root privileges. Pasta provides user-space networking without requiring `CAP_SYS_ADMIN` or root access. In spawn mode, pasta creates the namespace and runs your command inside it with full network connectivity.

### How filtering works

1. Pasta creates an isolated user+network namespace
2. An init script runs inside with `CAP_NET_ADMIN` to apply iptables rules
3. The capability is dropped before your command executes
4. Your command runs unprivileged and cannot modify the firewall rules

This ensures filtering decisions made at launch cannot be bypassed by the sandboxed application.

### Hostname resolution

Hostnames are resolved to IP addresses **at sandbox startup**. This is a fundamental limitation:

- Iptables rules are static - they don't support hostname-based filtering
- DNS resolution is dynamic - `github.com` might resolve to different IPs over time
- The sandbox's isolated namespace makes runtime DNS monitoring impractical without a proxy

**If you're using hostname-based filtering:**

- DNS lookups use your host machine's DNS before the sandbox starts
- If a hostname fails to resolve, execution halts with an error
- Services using CDNs or load balancers may rotate IPs during long-running sessions

For most use cases this works fine. If a service changes IP during execution, traffic to the new IP won't match your rules. For strict security requirements, use IP/CIDR filters instead of hostnames.

### Audit mode

Audit mode captures all network traffic to a pcap file without filtering. After the sandbox exits, a summary shows:

- Unique destinations contacted
- Bytes sent/received per destination
- Hostname mappings (from observed DNS responses)

The pcap file can be opened in Wireshark for detailed analysis.

### Requirements

Network filtering requires:
- `pasta` (install the `passt` package)
- `iptables` (for rule application)
- `ip6tables` (only if filtering IPv6 traffic)
- `setpriv` or `capsh` (for dropping capabilities)

The TUI shows installation commands if dependencies are missing.

## Development

```bash
# Run directly from source
uv run python src/cli.py -- bash

# Build single-file executable
./build.py

# Run built version
./bui -- bash

# Run tests
uv run --with pytest --with pytest-cov --with pytest-asyncio --with textual pytest tests/ -v

# With coverage
uv run --with pytest --with pytest-cov --with pytest-asyncio --with textual pytest tests/ --cov=src --cov-report=term-missing
```

### Code Layout

```
src/
├── cli.py              # Entry point, argument parsing
├── app.py              # Main Textual App (composes UI, orchestrates mixins)
├── bwrap.py            # bwrap command generation and execution
├── profiles.py         # Profile save/load
├── detection.py        # Path detection and resolution
│
├── net/                # Network filtering module
│   ├── __init__.py     # Module exports
│   ├── pasta.py        # pasta network namespace wrapper
│   ├── iptables.py     # iptables rule generation
│   └── utils.py        # Hostname resolution, validation, etc.
│
├── model/              # Data models (what gets configured)
│   ├── config.py       # SandboxConfig - the main configuration object
│   ├── network_filter.py
│   ├── groups.py       # Option groups (filesystem, network, etc.)
│   └── ...
│
├── controller/         # Event handling mixins (mixed into App)
│   ├── directories.py  # Directory binding events
│   ├── environment.py  # Environment variable events
│   ├── network.py      # Network filtering events
│   ├── overlays.py     # Overlay events
│   └── execute.py      # Execute/run events
│
└── ui/                 # UI components
    ├── tabs/           # Tab composition (one file per tab)
    │   ├── directories.py
    │   ├── network.py
    │   └── ...
    ├── widgets.py      # Reusable widgets
    ├── modals.py       # Modal dialogs
    ├── ids.py          # Widget IDs
    └── styles.css      # Textual CSS
```

**Key patterns:**
- `model/` defines data structures, `controller/` handles events, `ui/` renders
- Each tab has a composition function in `ui/tabs/` and event handlers in `controller/`
- `app.py` inherits from controller mixins and composes the full UI

## License

MIT
