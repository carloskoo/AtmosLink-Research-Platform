import argparse
import json
import struct
import time
from dataclasses import asdict, dataclass
from typing import Optional

import serial


@dataclass
class WindReading:
    wind_speed_ms: Optional[float]
    wind_direction_deg: Optional[float]
    wind_gust_ms: Optional[float]
    wind_ok: int
    error: Optional[str] = None
    raw_registers: Optional[list[int]] = None


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


def build_read_holding_registers_request(
    slave_id: int,
    start_register: int,
    quantity: int,
) -> bytes:
    frame = bytearray()
    frame.append(slave_id)
    frame.append(0x03)
    frame.extend(struct.pack(">H", start_register))
    frame.extend(struct.pack(">H", quantity))

    crc = modbus_crc(frame)
    frame.extend(struct.pack("<H", crc))

    return bytes(frame)


def validate_response(response: bytes, slave_id: int, expected_registers: int) -> None:
    expected_length = 5 + expected_registers * 2

    if len(response) != expected_length:
        raise ValueError(
            f"Longitud inválida: esperado={expected_length}, recibido={len(response)}, data={response.hex(' ')}"
        )

    data = response[:-2]
    received_crc = struct.unpack("<H", response[-2:])[0]
    calculated_crc = modbus_crc(data)

    if received_crc != calculated_crc:
        raise ValueError(
            f"CRC inválido: recibido=0x{received_crc:04X}, calculado=0x{calculated_crc:04X}, data={response.hex(' ')}"
        )

    if response[0] != slave_id:
        raise ValueError(f"Slave ID inválido: esperado={slave_id}, recibido={response[0]}")

    if response[1] != 0x03:
        raise ValueError(f"Función Modbus inválida: esperado=0x03, recibido=0x{response[1]:02X}")

    if response[2] != expected_registers * 2:
        raise ValueError(
            f"Byte count inválido: esperado={expected_registers * 2}, recibido={response[2]}"
        )


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
        time.sleep(0.05)

        ser.write(request)
        ser.flush()

        response = ser.read(expected_length)

    validate_response(response, slave_id, quantity)
    return parse_registers(response)


def convert_wind_registers(
    registers: list[int],
    scale_speed: float = 10.0,
    scale_direction: float = 1.0,
) -> WindReading:
    """
    Conversión preliminar para sensores integrados tipo XS-WSDS01 RS485.

    Suposición inicial:
      registro 0 = velocidad del viento * 10
      registro 1 = dirección del viento en grados
      registro 2 = ráfaga * 10, si existe

    Cuando tengamos la tabla Modbus exacta del fabricante, solo ajustaremos:
      start_register
      quantity
      escala de velocidad
      escala de dirección
    """

    if len(registers) < 2:
        return WindReading(
            wind_speed_ms=None,
            wind_direction_deg=None,
            wind_gust_ms=None,
            wind_ok=0,
            error="registros insuficientes",
            raw_registers=registers,
        )

    speed_raw = registers[0]
    direction_raw = registers[1]
    gust_raw = registers[2] if len(registers) >= 3 else speed_raw

    wind_speed_ms = speed_raw / scale_speed
    wind_direction_deg = direction_raw / scale_direction
    wind_gust_ms = gust_raw / scale_speed

    if wind_speed_ms < 0 or wind_speed_ms > 100:
        return WindReading(None, None, None, 0, f"velocidad fuera de rango: {wind_speed_ms}", registers)

    if wind_direction_deg < 0 or wind_direction_deg > 360:
        return WindReading(None, None, None, 0, f"dirección fuera de rango: {wind_direction_deg}", registers)

    if wind_gust_ms < 0 or wind_gust_ms > 150:
        return WindReading(None, None, None, 0, f"ráfaga fuera de rango: {wind_gust_ms}", registers)

    return WindReading(
        wind_speed_ms=round(wind_speed_ms, 2),
        wind_direction_deg=round(wind_direction_deg, 1),
        wind_gust_ms=round(wind_gust_ms, 2),
        wind_ok=1,
        error=None,
        raw_registers=registers,
    )


def read_wind_sensor(
    port: str = "/dev/ttyUSB0",
    baudrate: int = 4800,
    slave_id: int = 1,
    start_register: int = 0,
    quantity: int = 3,
    timeout: float = 2.0,
    scale_speed: float = 10.0,
    scale_direction: float = 1.0,
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

        return convert_wind_registers(
            registers=registers,
            scale_speed=scale_speed,
            scale_direction=scale_direction,
        )

    except Exception as e:
        return WindReading(
            wind_speed_ms=None,
            wind_direction_deg=None,
            wind_gust_ms=None,
            wind_ok=0,
            error=str(e),
            raw_registers=None,
        )


def reading_to_weather_fields(reading: WindReading) -> dict:
    return {
        "wind_speed_ms": reading.wind_speed_ms,
        "wind_direction_deg": reading.wind_direction_deg,
        "wind_gust_ms": reading.wind_gust_ms,
        "wind_ok": reading.wind_ok,
    }


def main():
    parser = argparse.ArgumentParser(description="AtmosLink RS485 Wind Sensor Test")

    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=4800)
    parser.add_argument("--slave-id", type=int, default=1)
    parser.add_argument("--start-register", type=int, default=0)
    parser.add_argument("--quantity", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--scale-speed", type=float, default=10.0)
    parser.add_argument("--scale-direction", type=float, default=1.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    while True:
        reading = read_wind_sensor(
            port=args.port,
            baudrate=args.baudrate,
            slave_id=args.slave_id,
            start_register=args.start_register,
            quantity=args.quantity,
            timeout=args.timeout,
            scale_speed=args.scale_speed,
            scale_direction=args.scale_direction,
        )

        if args.json:
            print(json.dumps(asdict(reading), ensure_ascii=False))
        else:
            print(reading)

        if not args.loop:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
