import sys

from egse.process import SubProcess

from cgse_dummy.dummy_cs import DummyProxy


def test_start_dummy_cs():
    print()

    proc = SubProcess(
        "Dummy CS", [sys.executable, "-m", "cgse_dummy.dummy_cs", "start"]
    )
    proc.execute()

    with DummyProxy() as dummy:
        assert dummy.info() == "DUMMY INSTRUMENTS, DAQ-1234, 0.0.2, SIMULATOR"
        assert -180.0 <= dummy.get_value() <= 25.0
        print(f"{dummy.get_value() = }")

    proc.quit()
