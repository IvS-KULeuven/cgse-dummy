from cgse_dummy.dummy_devif import DummyEthernetInterface

def test_connect():

    dev = DummyEthernetInterface()

    dev.connect()

    response = dev.query("*IDN?")
    response = response.decode()

    assert "DUMMY INSTRUMENTS" in response
    assert "DAQ-1234" in response

    dev.disconnect()
