"""
Driver placeholder for XS-WSDS01 RS485/Modbus wind sensor.

This module is prepared for future integration after Modbus registers
are identified using a USB-RS485 adapter.
"""


def read_wind():
    return {
        "wind_speed_ms": None,
        "wind_direction_deg": None,
        "wind_gust_ms": None,
        "wind_ok": 0,
    }
