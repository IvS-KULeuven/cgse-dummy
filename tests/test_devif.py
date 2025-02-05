"""
Prerequisites:

All unit tests assume that the dummy device simulator is already running. You can start the simulator
with the following command:

    $ cgse dummy start-sim

"""

from cgse_dummy.dummy_devif import DummyEthernetInterface


def test_connect_disconnect():

    dev = DummyEthernetInterface()

    dev.connect()
    assert dev.is_connected()

    dev.disconnect()
    assert not dev.is_connected()


def test_id():

    dev = DummyEthernetInterface()
    dev.connect()

    response = dev.query("*IDN?")
    response = response.decode()

    assert "DUMMY INSTRUMENTS" in response
    assert "DAQ-1234" in response

    dev.disconnect()


def test_send_request():

    from cgse_dummy.dummy_sim import send_request
    response = send_request("*IDN?")

    assert response is None
