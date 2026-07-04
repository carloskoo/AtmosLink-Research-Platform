import argparse
import struct
import time
from dataclasses import dataclass

import serial


@dataclass
class WindReading:
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    wind_gust_ms: float | None
    wind_ok: int
    error: str | None = None


def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1

    return crc


def build_read_holding_registers_request(slave_id: int, start_register: int, quantity: int) -> bytes:
    frame = bytearray()
    frame.append(slave_id)
    frame.append(0x03)
    frame.extend(struct.pack(">H", start_register))
    frame.extend(struct.pack(">H", quantity))

    crc = modbus_crc(frame)
    frame.extend(struct.pack("<H", crc))

    return bytes(frame)


def validate_response(response: bytes, slave_id: int, expected_registers: int) -> bool:
    if len(response) < 5:
        return False

    data = response[:-2]
    received_crc = struct.unpack("<H", response[-2:])[0]
    calculated_crc = modbus_crc(data)

    if received_crc != calculated_crc:
        return False

    if response[0] != slave_id:
        return False

    if response[1] != 0x03:
        return False

    if response[2] != expected_registers * 2:
        return False

    return True


def parse_registers(response: bytes) -> list[int]:
    byte_count = response[2]
    payload = response[3:3 + byte_count]

    registers = []

    for i in range(0, len(payload), 2):
        registers.append(struct.unpack(">H", payload[i:i + 2])[0])

    return registers


def read_modbus_registers(
    port: str,
    baudrate: int,
    slave_id: int,
    start_register: int,
    quantity: int,
    timeout: float,
) -> list[int]:
    request = build_read_holding_registers_request(
        slave_id=slave_id,
        start_register=start_register,
        quantity=quantity,
    )

    expected_length = 5 + quantity * 2

    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity=serial.PARITY_NONE,
        stopbits=1,
        timeout=timeout,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        ser.write(request)
        ser.flush()

        response = ser.read(expected_length)

    if not validate_response(response, slave_id, quantity):
        raise ValueError(f"Respuesta Modbus inválida: {response.hex(' ')}")

    return parse_registers(response)


def convert_wind_registers(registers: list[int]) -> WindReading:
    """
    Conversión preliminar para anemómetro RS485 tipo XS-WSDS01.

    Suposición inicial:
    register[0] = velocidad del viento * 10
    register[1] = dirección del viento en grados
    register[2] = ráfaga * 10, si existe

    Esta función podrá ajustarse cuando tengamos la tabla Modbus exacta del fabricante.
    """

    if len(registers) < 2:
        return WindReading(None, None, None, 0, "registros insuficientes")

    speed_raw = registers[0]
    direction_raw = registers[1]
    gust_raw = registers[2] if len(registers) >= 3 else speed_raw

    wind_speed_ms = speed_raw / 10.0
    wind_direction_deg = float(direction_raw)
    wind_gust_ms = gust_raw / 10.0

    if wind_speed_ms < 0 or wind_speed_ms > 100:
        return WindReading(None, None, None, 0, f"velocidad fuera de rango: {wind_speed_ms}")

    if wind_direction_deg < 0 or wind_direction_deg > 360:
        return WindReading(None, None, None, 0, f"dirección fuera de rango: {wind_direction_deg}")

    if wind_gust_ms < 0 or wind_gust_ms > 150:
        return WindReading(None, None, None, 0, f"ráfaga fuera de rango: {wind_gust_ms}")

    return WindReading(
        wind_speed_ms=round(wind_speed_ms, 2),
        wind_direction_deg=round(wind_direction_deg, 1),
        wind_gust_ms=round(wind_gust_ms, 2),
        wind_ok=1,
        error=None,
    )


def read_wind_sensor(
    port: str = "/dev/ttyUSB0",
    baudrate: int = 4800,
    slave_id: int = 1,
    start_register: int = 0,
    quantity: int = 3,
    timeout: float = 2.0,
) -> WindReading:
    try:
        registers = read_modbus_registers(
            port=port,
            baudrate=baudrate,
            slave_id=slave_id,
            start_register=start_register,
            quantity=quantity,
            timeout=timeout,
        )

        return convert_wind_registers(registers)

    except Exception as e:
        return WindReading(
            wind_speed_ms=None,
            wind_direction_deg=None,
            wind_gust_ms=None,
            wind_ok=0,
            error=str(e),
        )


def main():
    parser = argparse.ArgumentParser(description="AtmosLink RS485 Wind Sensor Test")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=4800)
    parser.add_argument("--slave-id", type=int, default=1)
    parser.add_argument("--start-register", type=int, default=0)
    parser.add_argument("--quantity", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)

    args = parser.parse_args()

    while True:
        reading = read_wind_sensor(
            port=args.port,
            baudrate=args.baudrate,
            slave_id=args.slave_id,
            start_register=args.start_register,
            quantity=args.quantity,
            timeout=args.timeout,
        )

        print(reading)

        if not args.loop:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
