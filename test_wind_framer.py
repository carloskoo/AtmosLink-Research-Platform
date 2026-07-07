from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB1"

client = ModbusSerialClient(
    port=PORT,
    framer="rtu",
    baudrate=9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=2,
    retries=1
)

print("Conectado:", client.connect())

try:
    rr = client.read_holding_registers(address=0, count=10, device_id=1)
    print(rr)
    if rr and not rr.isError():
        print("Registros:", rr.registers)
finally:
    client.close()
