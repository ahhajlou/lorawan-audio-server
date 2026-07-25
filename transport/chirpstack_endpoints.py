class ChirpStackMqttEndpoint:
    def __init__(self):
        pass

    def get_device_downlink(self, app_id, dev_eui) -> str:
        return f"application/{app_id}/device/{dev_eui}/command/down"

    def get_event_up(self) -> str:
        return "application/+/device/+/event/up"

    def get_event_join(self) -> str:
        return "application/+/device/+/event/join"

    def get_event_txack(self) -> str:
        return "application/+/device/+/event/txack"
