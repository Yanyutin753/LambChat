"""Tests for version utilities."""

from src.kernel.version_utils import has_new_version, normalize_version


class TestVersionUtils:
    """Test cases for version utilities."""

    def test_normalize_version(self):
        """Test version string normalization."""
        assert normalize_version("v1.2.0") == "1.2.0"
        assert normalize_version("1.2.0") == "1.2.0"
        assert normalize_version("v2.0.0-beta") == "2.0.0-beta"
        assert normalize_version("") == ""
        assert normalize_version("v") == ""

    def test_has_new_version_with_update(self):
        """Test version comparison with newer version."""
        assert has_new_version("1.0.0", "1.2.0") is True
        assert has_new_version("1.0.0", "2.0.0") is True
        assert has_new_version("0.9.0", "1.0.0") is True
        assert has_new_version("v1.0.0", "v1.2.0") is True

    def test_has_new_version_no_update(self):
        """Test version comparison with no newer version."""
        assert has_new_version("1.2.0", "1.0.0") is False
        assert has_new_version("1.2.0", "1.2.0") is False
        assert has_new_version("2.0.0", "1.0.0") is False

    def test_has_new_version_with_none(self):
        """Test version comparison with None."""
        assert has_new_version("1.0.0", None) is False

    def test_has_new_version_fallback_comparison(self):
        """Test fallback to string comparison with invalid current version."""
        # Invalid version will cause packaging to raise an exception
        # Fallback uses string comparison: "1.0.0" > "invalid" = False
        assert has_new_version("invalid", "1.0.0") is False
        # "invalid2" > "invalid" = True in string comparison
        assert has_new_version("invalid", "invalid2") is True
