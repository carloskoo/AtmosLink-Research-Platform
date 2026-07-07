from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB1"

DIRECTIONS_16 = {
    0: "N", 1: "NNE", 2: "NE", 3: "ENE",
    4: "E", 5: "ESE", 6: "SE", 7: "SSE",
    8: "S", 9: "SSW", 10: "SW", 11: "WSW",
    12: "W", 13: "WNW", 14: "NW", 15: "NNW",
}

client = ModbusSerialClient(
    port=PORT,
    baudrate=9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=1,
    retries=0
)

if not client.connect():
    print("No se pudo abrir", PORT)
    raise SystemExit

while True:
    try:
        rr = client.read_holding_registers(address=0, count=10, device_id=1)

        if rr and not rr.isError():
            regs = rr.registers
            speed = regs[0] / 10.0
            direction_code = regs[1]
            direction = DIRECTIONS_16.get(direction_code, "UNKNOWN")
            direction_deg = direction_code * 22.5

            print(
                f"Viento: {speed:.1f} m/s | "
                f"Dirección código: {direction_code} | "
                f"Dirección: {direction} | "
                f"Grados: {direction_deg} | "
                f"Registros: {regs}"
            )
        else:
            print("Sin respuesta:", rr)

    except Exception as e:
        print("ERROR:", e)

    time.sleep(2)
