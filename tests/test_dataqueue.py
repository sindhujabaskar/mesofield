from mesofield.io.manager import DataQueue, DataManager
import pandas as pd


def test_dataqueue_basic():
    dq = DataQueue()
    dq.push("dev1", 123)
    pkt = dq.pop()
    assert pkt.device_id == "dev1"
    assert pkt.payload == 123
    assert dq.empty()


class _DummyDevice:
    device_type = "dummy"
    device_id = "d1"
    def __init__(self):
        self.data_callback = None

    def emit(self, val):
        if self.data_callback:
            self.data_callback(val)


class _QueueDevice:
    device_type = "dummy"
    device_id = "d2"

    class Event:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, val):
            for cb in self._callbacks:
                cb(val)

    def __init__(self):
        self.data_event = self.Event()

    def emit(self, val):
        self.data_event.emit(val)


def test_manager_device_connection():
    dm = DataManager()
    dev = _DummyDevice()
    dm.register_hardware_device(dev)
    dev.emit(42)
    pkt = dm.data_queue.pop()
    assert pkt.device_id == "d1"
    assert pkt.payload == 42


def test_manager_queue_protocol():
    dm = DataManager()
    dev = _QueueDevice()
    dm.register_hardware_device(dev)
    dev.emit(7)
    pkt = dm.data_queue.pop()
    assert pkt.device_id == "d2"
    assert pkt.payload == 7


def test_queue_logging(tmp_path):
    dm = DataManager()
    log = tmp_path / "stream.csv"
    dm.start_queue_logger(str(log))
    dev = _QueueDevice()
    dm.register_hardware_device(dev)
    dev.emit(1)
    dev.emit(2)
    dm.stop_queue_logger()
    df = pd.read_csv(log)
    assert list(df["payload"]) == [1, 2]
