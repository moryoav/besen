"""Shared pytest setup."""

import pytest
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Keep the Home Assistant serializer and snapshot folder across versions."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
