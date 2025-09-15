import datetime

from cgse_dummy.dummy_sim import _VERSION
from cgse_dummy.dummy_sim import send_command
from cgse_dummy.dummy_sim import send_request


def test_send_request():
    response = send_request("*IDN?")

    parts = response.decode().strip().split(", ")

    assert len(parts) == 4

    manufacturer, model, sn, version = parts
    assert (
        manufacturer == "DUMMY INSTRUMENTS"
    )  # check the settings.yaml if this test fails
    assert model == "DAQ-1234"  # check the settings.yaml if this test fails
    assert sn == "SN2025-X23-5"  # check the settings.yaml if this test fails
    assert version == _VERSION


def test_info():
    response = send_request("info").decode().strip()

    assert "DUMMY INSTRUMENTS" in response
    assert "0.0.2" in response


def test_get_value():
    response = send_request("get_value").decode().strip()
    value_1 = float(response)

    assert -185.0 < value_1 < 30.0

    response = send_request("get_value").decode().strip()
    value_2 = float(response)

    assert value_1 != value_2


def test_system_time():
    send_command(":SYST:TIME 2025, 10, 10, 12, 12, 00")

    response = send_request(":SYST:TIME?").decode().strip()
    sys_time = datetime.datetime.strptime(response, "%a %b %d %H:%M:%S %Y")

    # it shouldn't take 2s to execute this test!
    assert sys_time <= datetime.datetime(2025, 10, 10, 12, 12, 2)
