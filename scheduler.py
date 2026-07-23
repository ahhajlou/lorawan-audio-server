class FlushScheduler:
    def __init__(self, buffers: BufferManager, transport: MqttTransport,
                 flush_interval_ms: int): ...

    def start(self) -> None:     # spawns daemon thread
    def stop(self) -> None:      # sets event, joins thread
    def _loop(self) -> None:     # the thread body
