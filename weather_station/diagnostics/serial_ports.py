from pymodbus.client import ModbusSerialClient

PORT="/dev/ttyUSB1"

client=ModbusSerialClient(
    port=PORT,
    baudrate=9600,
    timeout=1
)

client.connect()

for addr in range(0,40):

    try:

        rr=client.read_holding_registers(
            address=addr,
            count=1,
            device_id=1
        )

        if rr and not rr.isError():

            print(addr, rr.registers[0])

    except:
        pass

client.close()
