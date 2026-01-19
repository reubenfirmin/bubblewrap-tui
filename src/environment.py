"""Environment variable utilities for bui."""

from __future__ import annotations

import os


def get_system_env_vars() -> list[tuple[str, str]]:
    """Get sorted list of system environment variables.

    Returns:
        List of (name, value) tuples sorted by name
    """
    return sorted(os.environ.items())


def get_all_env_var_names() -> set[str]:
    """Get set of all environment variable names.

    Returns:
        Set of environment variable names
    """
    return set(os.environ.keys())


def split_env_vars_into_columns(
    env_vars: list[tuple[str, str]], num_columns: int = 3
) -> list[list[tuple[str, str]]]:
    """Split environment variables into columns for display.

    Args:
        env_vars: List of (name, value) tuples
        num_columns: Number of columns to split into

    Returns:
        List of lists, each containing env vars for one column
    """
    if not env_vars:
        return [[] for _ in range(num_columns)]

    chunk_size = max(1, len(env_vars) // num_columns)
    columns = []

    for i in range(num_columns):
        start = i * chunk_size
        if i == num_columns - 1:
            # Last column gets the remainder
            columns.append(env_vars[start:])
        else:
            columns.append(env_vars[start : start + chunk_size])

    return columns
