"""Tests for environment variable utilities."""

from unittest.mock import patch

import pytest

from environment import get_all_env_var_names, get_system_env_vars, split_env_vars_into_columns


class TestGetSystemEnvVars:
    """Test get_system_env_vars() function."""

    @patch.dict("os.environ", {"Z_VAR": "z", "A_VAR": "a", "M_VAR": "m"}, clear=True)
    def test_returns_sorted_list(self):
        """Returns sorted list of (name, value) tuples."""
        result = get_system_env_vars()
        assert result == [("A_VAR", "a"), ("M_VAR", "m"), ("Z_VAR", "z")]

    @patch.dict("os.environ", {}, clear=True)
    def test_empty_environment(self):
        """Returns empty list for empty environment."""
        result = get_system_env_vars()
        assert result == []

    @patch.dict("os.environ", {"PATH": "/usr/bin", "HOME": "/home/user"}, clear=True)
    def test_returns_tuples(self):
        """Each item is a (name, value) tuple."""
        result = get_system_env_vars()
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2


class TestGetAllEnvVarNames:
    """Test get_all_env_var_names() function."""

    @patch.dict("os.environ", {"PATH": "/usr/bin", "HOME": "/home/user"}, clear=True)
    def test_returns_set(self):
        """Returns a set of env var names."""
        result = get_all_env_var_names()
        assert isinstance(result, set)
        assert result == {"PATH", "HOME"}

    @patch.dict("os.environ", {}, clear=True)
    def test_empty_environment(self):
        """Returns empty set for empty environment."""
        result = get_all_env_var_names()
        assert result == set()


class TestSplitEnvVarsIntoColumns:
    """Test split_env_vars_into_columns() function."""

    def test_splits_into_three_columns_by_default(self):
        """Default is 3 columns."""
        env_vars = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5"), ("F", "6")]
        result = split_env_vars_into_columns(env_vars)
        assert len(result) == 3

    def test_splits_into_specified_columns(self):
        """Can specify number of columns."""
        env_vars = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4")]
        result = split_env_vars_into_columns(env_vars, num_columns=2)
        assert len(result) == 2

    def test_distributes_evenly(self):
        """Items distributed evenly across columns."""
        env_vars = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5"), ("F", "6")]
        result = split_env_vars_into_columns(env_vars, num_columns=3)
        # Each column should have 2 items
        assert len(result[0]) == 2
        assert len(result[1]) == 2
        assert len(result[2]) == 2

    def test_last_column_gets_remainder(self):
        """Last column gets remainder when not evenly divisible."""
        env_vars = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5")]
        result = split_env_vars_into_columns(env_vars, num_columns=3)
        # First two columns: 1 item each (5 // 3 = 1)
        # Last column: remainder (5 - 2 = 3)
        assert len(result[0]) == 1
        assert len(result[1]) == 1
        assert len(result[2]) == 3

    def test_empty_input(self):
        """Empty input returns list of empty lists."""
        result = split_env_vars_into_columns([])
        assert len(result) == 3
        assert all(col == [] for col in result)

    def test_fewer_items_than_columns(self):
        """Works with fewer items than columns."""
        env_vars = [("A", "1")]
        result = split_env_vars_into_columns(env_vars, num_columns=3)
        assert len(result) == 3
        assert result[0] == [("A", "1")]
        # Subsequent columns empty when using last gets remainder
        # Actually with chunk_size = max(1, 1//3) = 1, first gets item, rest get []
        assert result[2] == []

    def test_preserves_order(self):
        """Order is preserved within columns."""
        env_vars = [("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", "5"), ("F", "6")]
        result = split_env_vars_into_columns(env_vars, num_columns=3)
        # Flatten and check order
        flattened = result[0] + result[1] + result[2]
        assert flattened == env_vars
