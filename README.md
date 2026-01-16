# bui - Bubblewrap TUI

A terminal user interface for configuring and launching [bubblewrap](https://github.com/containers/bubblewrap) sandboxes.

Instead of memorizing dozens of `bwrap` flags, visually configure your sandbox and see the generated command before execution.

## Status

- This is both alpha quality and lightly tested. That said it doesn't do anything except generate (and run, on demand) a bwrap command, so is mostly harmless. 
- PRs and bug reports are welcomed. Feature requests will be considered. :) 

## Requirements

- [uv](https://github.com/astral-sh/uv)
- [bubblewrap](https://github.com/containers/bubblewrap)

## Installation

### Install uv

See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for your platform.

### Get bui

```bash
# Download the script
curl -O https://raw.githubusercontent.com/reubenfirmin/bubblewrap-tui/main/bui
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
