#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
Build script for bui - concatenates src/ modules into a single executable script.

Usage: ./build.py
"""

from pathlib import Path

# Header for the generated script (shebang + uv metadata)
HEADER = '''#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["textual>=0.89.0"]
# ///
"""
Bubblewrap TUI - A visual interface for configuring bubblewrap sandboxes.

Usage: bui -- <command> [args...]
"""
'''

# Order matters - modules must be concatenated in dependency order
MODULE_ORDER = [
    "detection.py",  # No dependencies
    "config.py",     # Depends on detection (uses find_* functions)
    "widgets.py",    # Depends on config (uses OverlayConfig, etc.)
    "app.py",        # Depends on widgets, config, styles
    "cli.py",        # Depends on app
]

# Local modules (imports to filter out)
LOCAL_MODULES = {"detection", "config", "widgets", "app", "cli", "styles"}


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
            is_local = any(stripped.startswith(f'from {mod} ') or stripped == f'import {mod}'
                          for mod in LOCAL_MODULES)
            if not is_local:
                imports.add(line)
        else:
            in_imports = False
            non_import_lines.append(line)

        i += 1

    return imports, '\n'.join(non_import_lines)


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
        if 'Path(__file__).parent / "styles.css"' in line:
            # Insert inlined CSS
            result.append(f'APP_CSS = """{css_content}"""')
            skip_css_load = True
            continue

        result.append(line)

    return '\n'.join(result)


def build():
    """Build the single-file bui script from src/ modules."""
    src_dir = Path(__file__).parent / "src"
    output_path = Path(__file__).parent / "bui"

    if not src_dir.exists():
        print(f"Error: {src_dir} does not exist")
        return False

    # Load CSS file
    css_path = src_dir / "styles.css"
    if not css_path.exists():
        print(f"Error: {css_path} does not exist")
        return False
    css_content = css_path.read_text()

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

        imports, code = extract_imports(content)
        all_imports.update(imports)

        # Add module separator comment
        all_code.append(f"\n# === {module_name} ===\n")
        all_code.append(code.strip())

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


if __name__ == "__main__":
    build()
