import sys

from egse.process import SubProcess

from cgse_dummy.dummy_cs import DummyProxy


def test_start_dummy_cs():

    proc = SubProcess("Dummy CS", [sys.executable, "-m", "cgse_dummy.dummy_cs", "start"])
    proc.execute()

    with DummyProxy() as dummy:
        assert dummy.info() == "DUMMY INSTRUMENTS, MODEL DAQ-1234, SIMULATOR"
        assert 0 <= dummy.get_value() <= 1.0

    proc.quit()
