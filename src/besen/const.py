"""Constants for the Besen client library."""

from typing import Final

DEFAULT_PIN: Final = "123456"

PACKET_HEADER: Final = b"\x06\x01"
PACKET_MIN_LENGTH: Final = 25

WRITE_UUID: Final = "0000fff2-0000-1000-8000-00805f9b34fb"
READ_UUID: Final = "0000fff1-0000-1000-8000-00805f9b34fb"
REV_WRITE_UUID: Final = "0003cdd2-0000-1000-8000-00805f9b0131"
REV_READ_UUID: Final = "0003cdd1-0000-1000-8000-00805f9b0131"
NEW_BOARD_WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NEW_BOARD_READ_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

OLD_BOARD_SERVICE_PREFIXES: Final = ()
REV_BOARD_SERVICE_PREFIXES: Final = ("0003cdd0-",)
NEW_BOARD_SERVICE_PREFIXES: Final = ("0000ffe5-", "0000ffe0-")

LOGIN_TIMEOUT: Final = 45
LOGIN_ATTEMPTS: Final = 3
SILENT_LOGIN_TIMEOUT: Final = 10
LOGIN_REQUEST_RETRY_INTERVAL: Final = 5
CONNECT_TIMEOUT: Final = 65.0
CONNECT_ATTEMPTS: Final = 5
DISCONNECT_TIMEOUT: Final = 10.0
MESSAGE_TIMEOUT: Final = 45
RECONNECT_DELAY: Final = 5
CLOCK_SYNC_INTERVAL: Final = 3600

MIN_CHARGE_AMPS: Final = 6
FALLBACK_MAX_CHARGE_AMPS: Final = 32
DEFAULT_CHARGE_AMPS: Final = 6

ERRORS: Final = {
    0: "Relay Stick Error",
    1: "Relay Stick Error",
    2: "Relay Stick Error",
    3: "OFFLINE",
    4: "CC Error",
    5: "CP Error",
    6: "Emergency Stop",
    7: "Over Temperature",
    8: "Over Temperature",
    9: "Unknown",
    10: "Leakage Protection",
    11: "Short Circuit",
    12: "Over Current",
    13: "Ungrounded",
    14: "Over Voltage",
    15: "Low Voltage",
    25: "Input Power Error",
    26: "DLB Over Current - Mains overload",
    27: "Diode Short Circuit",
    28: "RTC Failure",
    29: "Flash Memory Failure",
    30: "EEPROM Failure",
    31: "Metering Module Failure",
    255: "No Error",
}

PLUG_STATE: Final = [
    "Unknown 0",
    "Disconnected",
    "Connected Unlocked",
    "Unknown 1",
    "Connected Locked",
    "Unknown 2",
    "Unknown 3",
    "Unknown 4",
    "Unknown 5",
]

OUTPUT_STATE: Final = [
    "Unknown 0",
    "Charging",
    "Idle",
    "Unknown 1",
    "Unknown 2",
    "Unknown 3",
    "Unknown 4",
    "Unknown 5",
    "Unknown 6",
]

CURRENT_STATE: Final = [
    "Fault",
    "Charging Fault 1",
    "Charging Fault 2",
    "Unknown 1",
    "Unknown 2",
    "Unknown 3",
    "Unknown 4",
    "Unknown 5",
    "Unknown 6",
    "Waiting for swipe",
    "Waiting for button",
    "Not Connected",
    "Ready to charge",
    "Charging",
    "Completed",
    "Unknown 7",
    "Completed Full Charge",
    "Unknown 8",
    "Unknown 9",
    "Charging Reservation",
    "Unknown 10",
]

CHARGING_STATUS: Final = {
    1: "Start",
    2: "Finish Charging",
    3: "Waiting",
    4: "Finished",
    5: "Finished",
    6: "Cancel",
    7: "Connect",
    8: "Fault",
    9: "Start",
    10: "Start",
    11: "Finish Charging",
}

CHARGING_STATUS_DESCRIPTIONS: Final = {
    1: "EV is connected, please press start",
    2: "Charging",
    3: "Charging has started, waiting for EV.",
    4: "Charging completed",
    5: "Charging completed",
    6: "Charging reservation.",
    7: "The plug is not connected, please start charging after connecting.",
    8: "See Error State",
    9: "Wait for the swipe to start",
    10: "Wait for the button to activate",
    11: "See Error State",
}

CHARGER_STATUS: Final = {
    1: 0,
    2: 1,
    3: 1,
    4: 0,
    5: 0,
    6: 0,
    7: 0,
    8: 0,
    9: 0,
    10: 0,
    11: 0,
}

TEMPERATURE_UNIT_ALIASES: Final = {"Celcius": "Celsius"}
TEMPERATURE_UNITS: Final = {"Celsius": 1, "Fahrenheit": 2}

LANGUAGES: Final = {
    "English": 1,
    "Italiano": 2,
    "Deutsch": 3,
    "Fran\u00e7ais": 4,
    "Espa\u00f1ol": 5,
    "\u05e2\u05d1\u05e8\u05d9\u05ea": 6,
    "Polski": 7,
    "\u4e2d\u6587": 8,
}

STOP_REASON: Final = {
    0: "The reservation was stopped in advance by app",
    1: "When the appointment time arrived, there was no rush",
    11: "App stop",
    12: "Card swiping stop",
    13: "Auto fill",
    14: "Fixed fee to",
    15: "Quantitative to",
    16: "Timed to",
    17: "Draw a gun",
    18: "End of power failure",
    19: "Fault, overcurrent",
    20: "Fault, short circuit",
    21: "Fault, main board over temperature",
    22: "Fault, over temperature of plug",
    23: "Fault, emergency stop pressed",
    24: "Key end",
    30: "Exceeding the maximum time of 48H",
    31: "Exceeding the maximum power of 400kwh",
    32: "Exceeding the maximum cost of 400 yuan",
}

CHARGE_START_ERROR: Final = {
    0: "No error",
    1: "The charging plug is not plugged in properly",
    2: "System error",
    3: "Charging",
    4: "System maintenance",
    5: "Incorrect set fee",
    6: "Incorrect set power consumption",
    7: "Incorrect set time",
    8: "Unknown reason",
    20: "Failed to start, already in reservation status",
}

CHARGE_START_RESERVATION: Final = {
    0: "No error",
    2: "Reservation failed, the system does not support reservation",
    3: "Reservation failed, the reservation time is more than 24 hours",
    4: "Reservation failed, the reservation time is earlier than the current time",
    5: "Reservation failed, system error",
    6: "Reservation failed, already in reservation status",
    7: "Reservation failed, already in charging status",
    8: "Reservation failed, the fixed fee is incorrect",
    9: "Reservation failed, the fixed power consumption is incorrect",
    10: "Reservation failed, the fixed time is incorrect",
}
