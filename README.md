# bui - Bubblewrap TUI

A terminal user interface for configuring and launching [bubblewrap](https://github.com/containers/bubblewrap) sandboxes.

Instead of memorizing dozens of `bwrap` flags, visually configure your sandbox and see the generated command before execution.

## Features

- **Directory Binding** - Browse and select directories to bind into the sandbox (read-only or read-write)
- **Environment Variables** - Keep, remove, or add custom environment variables. Import from `.env` files
- **System Paths** - Toggle common system paths (/usr, /bin, /lib, etc.)
- **Isolation Options** - Configure namespaces (user, PID, IPC, UTS, cgroup)
- **Network Control** - Enable or block network access
- **Live Preview** - See the generated `bwrap` command as you configure
- **Summary Tab** - Human-readable explanation of what your sandbox will do

## Requirements

- [uv](https://github.com/astral-sh/uv)
- [bubblewrap](https://github.com/containers/bubblewrap)

## Installation

### Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Get bui

```bash
# Clone or download the script
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/bubblewrap-tui/main/bui
chmod +x bui

# Run directly - uv handles Python and dependencies automatically
./bui -- your-command
```

## Usage

```bash
# Basic usage - sandbox a shell
./bui -- /bin/bash

# Sandbox a specific command
./bui -- python script.py

# Sandbox with arguments
./bui -- node server.js --port 3000
```

## License

MIT
