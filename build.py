#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
Build script for bui - concatenates src/ modules into a single executable script.

Usage: ./build.py [--bundle] [--clean]
"""

import argparse
import shutil
from pathlib import Path

# Header for the generated script (shebang + uv metadata)
HEADER = '''#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["textual>=0.89.0", "dpkt>=1.9.8"]
# ///
"""
Bubblewrap TUI - A visual interface for configuring bubblewrap sandboxes.

Usage: bui -- <command> [args...]
"""
'''

# Order matters - modules must be concatenated in dependency order
MODULE_ORDER = [
    "constants.py",                   # No dependencies - shared constants
    "fileutils.py",                   # No dependencies - file utilities
    "detection.py",                   # No dependencies (system detection)
    "environment.py",                 # No dependencies (env var utilities)
    "installer.py",                   # Profile installation
    "sandbox.py",                     # Sandbox lifecycle management
    "model/ui_field.py",              # No dependencies - UIField, Field, ConfigBase
    "model/bound_directory.py",       # No dependencies
    "model/overlay_config.py",        # No dependencies
    "model/network_filter.py",        # No dependencies - network filtering model
    "model/config_group.py",          # Depends on ui_field
    "model/config.py",                # Depends on config_group
    "model/fields/vfs.py",            # VFS field definitions
    "model/fields/system_paths.py",   # System path field definitions
    "model/fields/user.py",           # User field definitions
    "model/fields/isolation.py",      # Isolation/namespace field definitions
    "model/fields/process.py",        # Process field definitions
    "model/fields/network.py",        # Network field definitions
    "model/fields/desktop.py",        # Desktop integration field definitions
    "model/fields/environment.py",    # Environment field definitions
    "model/fields/__init__.py",       # Fields package re-exports
    "model/serializers.py",           # Custom to_args/to_summary functions
    "model/groups.py",                # Depends on config, config_group, ui_field, fields, serializers
    "model/sandbox_config.py",        # Depends on config_group, groups, network_filter
    "commandoutput.py",               # Command output formatting
    "net/utils.py",                   # Network utilities (resolve hostname, validate, etc.)
    "net/iptables.py",                # iptables rule generation
    "net/dns_proxy.py",               # DNS proxy generation for hostname filtering
    "net/pasta_install.py",           # pasta installation detection
    "net/pasta_args.py",              # pasta command argument generation
    "net/filtering.py",               # Network filtering validation/script generation
    "net/pasta_exec.py",              # pasta execution functions
    "net/pasta.py",                   # pasta re-exports for compatibility
    "net/audit.py",                   # Network audit/pcap analysis
    "net/__init__.py",                # Network module exports
    "bwrap.py",                       # Depends on detection, model (serialization/summary)
    "virtual_files.py",               # Virtual file management (depends on bwrap for user data)
    "profiles.py",                    # Depends on model (JSON serialization)
    "ui/ids.py",                      # No dependencies - widget ID constants (needed early for ids.X refs)
    "controller/validators.py",       # Validation functions for sync
    "controller/sync.py",             # UI ↔ Config sync (depends on validators)
    "ui/widgets/directory.py",        # Directory widgets (FilteredDirectoryTree, BoundDirItem)
    "ui/widgets/overlay.py",          # Overlay widget (OverlayItem)
    "ui/widgets/environment.py",      # Environment widgets (EnvVarItem, EnvVarRow, AddEnvDialog)
    "ui/widgets/sandbox.py",          # Sandbox widgets (DevModeCard, OptionCard)
    "ui/widgets/profiles.py",         # Profile widget (ProfileItem)
    "ui/widgets/network.py",          # Network widgets (PastaStatus, FilterModeRadio, FilterList, PortList)
    "ui/widgets/__init__.py",         # Widget package re-exports
    "ui/widgets.py",                  # Legacy re-export for compatibility
    "ui/helpers.py",                  # Depends on ui.widgets
    "ui/tabs/directories.py",         # Depends on ui.widgets
    "ui/tabs/environment.py",         # Depends on ui.widgets
    "ui/tabs/overlays.py",            # No widget dependencies
    "ui/tabs/sandbox.py",             # Depends on ui.widgets, model, detection
    "ui/tabs/network.py",             # Depends on ui.widgets, net
    "ui/tabs/summary.py",             # No dependencies
    "ui/tabs/profiles.py",            # No dependencies
    "ui/modals.py",                   # Profile modals - depends on profiles
    "controller/execute.py",          # Event handler - no ui deps
    "controller/directories.py",      # Event handler - depends on ui
    "controller/overlays.py",         # Event handler - depends on ui
    "controller/environment.py",      # Event handler - depends on ui
    "controller/network.py",          # Event handler - network filtering
    "app.py",                         # Depends on ui, model, profiles, controller, detection
    "command_execution.py",           # Command execution dispatch and cleanup
    "cli.py",                         # Depends on app, model, profiles, installer, net, command_execution
]

# Local modules (imports to filter out)
LOCAL_MODULES = {
    "constants", "fileutils", "detection", "environment", "installer", "sandbox", "profiles", "app", "cli", "styles", "bwrap",
    "commandoutput", "virtual_files", "command_execution",
    "net", "net.utils", "net.iptables", "net.dns_proxy", "net.pasta", "net.audit",
    "net.pasta_install", "net.pasta_args", "net.filtering", "net.pasta_exec",
    "model",
    "model.ui_field", "model.bound_directory", "model.overlay_config", "model.network_filter",
    "model.config_group", "model.config", "model.groups", "model.sandbox_config", "model.serializers",
    "model.fields", "model.fields.vfs", "model.fields.system_paths", "model.fields.user",
    "model.fields.isolation", "model.fields.process", "model.fields.network",
    "model.fields.desktop", "model.fields.environment",
    "controller", "controller.sync", "controller.directories", "controller.overlays",
    "controller.environment", "controller.execute", "controller.network",
    "controller.validators",
    "ui", "ui.ids", "ui.widgets", "ui.widgets.directory", "ui.widgets.overlay",
    "ui.widgets.environment", "ui.widgets.sandbox", "ui.widgets.profiles", "ui.widgets.network",
    "ui.helpers", "ui.modals",
    "ui.tabs", "ui.tabs.directories", "ui.tabs.environment", "ui.tabs.filesystem",
    "ui.tabs.overlays", "ui.tabs.sandbox", "ui.tabs.network", "ui.tabs.summary", "ui.tabs.profiles",
}


def extract_imports(content: str) -> tuple[set[str], str]:
    """Extract module-level import statements and return (imports, remaining code)."""
    imports = set()
    lines = content.split('\n')
    non_import_lines = []
    in_imports = True
    in_multiline_import = False
    current_import = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Handle multi-line imports
        if in_multiline_import:
            current_import.append(line)
            if ')' in line:
                # End of multi-line import
                full_import = '\n'.join(current_import)
                # Check if it's a local module import
                first_line = current_import[0].strip()
                is_local = any(first_line.startswith(f'from {mod} ') for mod in LOCAL_MODULES)
                if not is_local:
                    imports.add(full_import)
                current_import = []
                in_multiline_import = False
            i += 1
            continue

        # Skip empty lines and comments at the start
        if in_imports and (not stripped or stripped.startswith('#')):
            if stripped.startswith('#') and not stripped.startswith('# ///'):
                non_import_lines.append(line)
            i += 1
            continue

        # Only extract module-level imports (no indentation)
        if line and not line[0].isspace() and (stripped.startswith('from ') or stripped.startswith('import ')):
            # Check if it's a multi-line import
            if '(' in line and ')' not in line:
                in_multiline_import = True
                current_import = [line]
                i += 1
                continue

            # Single line import - filter out local module imports
            # Handle: 'from mod import X', 'import mod', 'import mod as alias'
            is_local = any(
                stripped.startswith(f'from {mod} ') or
                stripped == f'import {mod}' or
                stripped.startswith(f'import {mod} ')  # handles 'import X as Y'
                for mod in LOCAL_MODULES
            )
            if not is_local:
                imports.add(line)
        else:
            in_imports = False
            non_import_lines.append(line)

        i += 1

    return imports, '\n'.join(non_import_lines)


def strip_deferred_imports(code: str, local_modules: set[str]) -> str:
    """Remove deferred imports (inside functions) of local modules.

    These imports exist to avoid circular dependencies at module level,
    but in the concatenated output, all code is already available.
    """
    lines = code.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        # Check if this is an indented import of a local module
        if line and line[0].isspace():
            is_local_import = any(
                stripped.startswith(f'from {mod} import') or
                stripped == f'import {mod}' or
                stripped.startswith(f'import {mod} ')
                for mod in local_modules
            )
            if is_local_import:
                # Replace with pass to maintain valid syntax after if/else/etc
                indent = len(line) - len(line.lstrip())
                result.append(' ' * indent + 'pass  # (deferred import removed)')
                continue
        result.append(line)
    return '\n'.join(result)


def normalize_import(imp: str) -> tuple[str, set[str]]:
    """Normalize an import statement and extract module and names.

    Returns (module, {names}) or (full_import, set()) for simple imports.
    """
    imp = imp.strip()

    # Handle 'from X import Y, Z' or 'from X import (Y, Z)'
    if imp.startswith('from '):
        # Remove 'from ' prefix
        rest = imp[5:]
        if ' import ' in rest:
            module, names_part = rest.split(' import ', 1)
            # Clean up the names
            names_part = names_part.strip().strip('()')
            # Handle multi-line by joining and splitting
            names_part = ' '.join(names_part.split())
            names = {n.strip().rstrip(',') for n in names_part.replace('\n', ',').split(',') if n.strip()}
            return f'from {module} import', names

    # Simple import
    return imp, set()


def merge_imports(imports: set[str]) -> list[str]:
    """Merge imports from the same module."""
    # Group by module
    module_names: dict[str, set[str]] = {}
    simple_imports = []

    for imp in imports:
        module_prefix, names = normalize_import(imp)
        if names:
            if module_prefix not in module_names:
                module_names[module_prefix] = set()
            module_names[module_prefix].update(names)
        else:
            simple_imports.append(module_prefix)

    # Reconstruct imports
    result = []
    for module_prefix, names in sorted(module_names.items()):
        sorted_names = sorted(names)
        if len(sorted_names) <= 3:
            result.append(f'{module_prefix} {", ".join(sorted_names)}')
        else:
            # Multi-line format
            names_str = ',\n    '.join(sorted_names)
            result.append(f'{module_prefix} (\n    {names_str},\n)')

    result.extend(sorted(set(simple_imports)))
    return result


def sort_imports(imports: set[str]) -> str:
    """Sort and deduplicate imports: standard library, then third-party."""
    # First merge imports
    merged = merge_imports(imports)

    stdlib = []
    thirdparty = []
    future = []

    for imp in merged:
        if imp.startswith('from __future__'):
            future.append(imp)
        elif 'textual' in imp:
            thirdparty.append(imp)
        else:
            stdlib.append(imp)

    result = []
    if future:
        result.extend(sorted(future))
        result.append('')
    if stdlib:
        result.extend(sorted(stdlib))
        result.append('')
    if thirdparty:
        result.extend(sorted(thirdparty))
        result.append('')

    return '\n'.join(result)


def process_app_module(content: str, css_content: str) -> str:
    """Process app.py to inline the CSS."""
    # Replace the CSS file loading with inlined CSS
    lines = content.split('\n')
    result = []
    skip_css_load = False

    for line in lines:
        # Replace the CSS file loading line
        if 'Path(__file__).parent / "ui" / "styles.css"' in line:
            # Insert inlined CSS
            result.append(f'APP_CSS = """{css_content}"""')
            skip_css_load = True
            continue

        result.append(line)

    return '\n'.join(result)


def process_dns_proxy_module(content: str, script_content: str) -> str:
    """Process dns_proxy.py to inline the DNS proxy script."""
    lines = content.split('\n')
    result = []
    skip_until_assignment = False

    for line in lines:
        # Skip the _load_dns_proxy_script function and its call
        if 'def _load_dns_proxy_script()' in line:
            skip_until_assignment = True
            continue
        if skip_until_assignment:
            if line.startswith('DNS_PROXY_SCRIPT = _load_dns_proxy_script()'):
                # Replace with inlined script using repr() to properly escape quotes
                result.append(f'DNS_PROXY_SCRIPT = {repr(script_content)}')
                skip_until_assignment = False
            continue

        result.append(line)

    return '\n'.join(result)


def clean():
    """Remove __pycache__ directories and .pyc files."""
    root = Path(__file__).parent

    # Remove __pycache__ directories
    for pycache in root.rglob("__pycache__"):
        print(f"Removing {pycache}")
        shutil.rmtree(pycache)

    # Remove .pyc files
    for pyc_file in root.rglob("*.pyc"):
        print(f"Removing {pyc_file}")
        pyc_file.unlink()

    print("Clean complete")
    return True


def bundle():
    """Build the single-file bui script from src/ modules."""
    src_dir = Path(__file__).parent / "src"
    output_path = Path(__file__).parent / "bui"

    if not src_dir.exists():
        print(f"Error: {src_dir} does not exist")
        return False

    # Load CSS file
    css_path = src_dir / "ui" / "styles.css"
    if not css_path.exists():
        print(f"Error: {css_path} does not exist")
        return False
    css_content = css_path.read_text()

    # Load DNS proxy script
    dns_proxy_script_path = src_dir / "net" / "dns_proxy_script.py"
    if not dns_proxy_script_path.exists():
        print(f"Error: {dns_proxy_script_path} does not exist")
        return False
    dns_proxy_script_content = dns_proxy_script_path.read_text()

    all_imports = set()
    all_code = []

    for module_name in MODULE_ORDER:
        module_path = src_dir / module_name
        if not module_path.exists():
            print(f"Warning: {module_path} does not exist, skipping")
            continue

        content = module_path.read_text()

        # Special handling for app.py - inline CSS
        if module_name == "app.py":
            content = process_app_module(content, css_content)

        # Special handling for dns_proxy.py - inline DNS proxy script
        if module_name == "net/dns_proxy.py":
            content = process_dns_proxy_module(content, dns_proxy_script_content)

        imports, code = extract_imports(content)
        all_imports.update(imports)

        # Strip deferred imports of local modules (they're already concatenated)
        code = strip_deferred_imports(code, LOCAL_MODULES)

        # Add module separator comment
        all_code.append(f"\n# === {module_name} ===\n")
        all_code.append(code.strip())

        # After model/groups.py, add a namespace shim so 'groups.vfs_group' works
        if module_name == "model/groups.py":
            all_code.append('''

# Namespace shim for 'from model import groups' pattern
class _GroupsNamespace:
    def __getattr__(self, name):
        return globals()[name]
groups = _GroupsNamespace()
''')

        # After ui/ids.py, add a namespace shim so 'ids.CONSTANT' works
        if module_name == "ui/ids.py":
            all_code.append('''

# Namespace shim for 'import ui.ids as ids' pattern
class _IdsNamespace:
    def __getattr__(self, name):
        return globals()[name]
ids = _IdsNamespace()
''')

    # Combine everything
    output = HEADER
    output += sort_imports(all_imports)
    output += '\n'.join(all_code)
    output += '\n'

    # Write output
    output_path.write_text(output)
    output_path.chmod(0o755)

    print(f"Built {output_path} ({len(output.splitlines())} lines)")
    return True


def main():
    """Parse arguments and execute requested operations."""
    parser = argparse.ArgumentParser(description="Build script for bui")
    parser.add_argument("--bundle", action="store_true", help="Build the single-file executable")
    parser.add_argument("--clean", action="store_true", help="Remove __pycache__ and .pyc files")
    args = parser.parse_args()

    # Default to bundle if no flags specified
    if not args.bundle and not args.clean:
        args.bundle = True

    success = True
    if args.clean:
        success = clean() and success
    if args.bundle:
        success = bundle() and success

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
