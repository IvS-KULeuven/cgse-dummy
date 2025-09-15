"""
Prerequisites:

All unit tests assume that the dummy device simulator is already running. You can start the simulator
with the following command:

    $ cgse dummy start-sim

"""

from cgse_dummy.dummy_dev import Dummy


def test_connect_disconnect():
    dev = Dummy()

    dev.connect()
    assert dev.is_connected()

    dev.disconnect()
    assert not dev.is_connected()

    with Dummy() as dummy:
        assert dummy.is_connected()

    assert not dummy.is_connected()


def test_idn():
    from cgse_dummy.dummy_sim import _VERSION

    dev = Dummy()
    dev.connect()

    response = dev.query("*IDN?")

    parts = response.decode().strip().split(", ")

    assert len(parts) == 4

    manufacturer, model, sn, version = parts

    assert (
        manufacturer == "DUMMY INSTRUMENTS"
    )  # check the settings.yaml if this test fails
    assert model == "DAQ-1234"  # check the settings.yaml if this test fails
    assert sn == "SN2025-X23-5"  # check the settings.yaml if this test fails
    assert version == _VERSION

    dev.disconnect()
