from pathlib import Path

p = Path("weather_station/logger/logger_weather.py")
text = p.read_text(encoding="utf-8")

backup = p.with_suffix(".py.bak_serial_sync")
backup.write_text(text, encoding="utf-8")

old = '''            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
                logging.info("Puerto serie abierto")
                print("Puerto serie abierto")

                while True:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()

                    if not line:
                        continue

                    print("RX:", line)
'''

new = '''            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
                logging.info("Puerto serie abierto")
                print("Puerto serie abierto")

                # Sincronización inicial del puerto serie.
                # Algunos ESP32 envían fragmentos de trama al abrir el puerto.
                time.sleep(2)
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except Exception:
                    pass

                while True:
                    raw = ser.readline()
                    line = raw.decode("utf-8", errors="ignore").strip()

                    if not line:
                        continue

                    # Descartar fragmentos o mensajes informativos.
                    # La trama válida del firmware V3 debe iniciar con WSCSV.
                    if not line.startswith("WSCSV"):
                        print("RX_DESCARTADO:", line)
                        continue

                    print("RX:", line)
'''

if old not in text:
    raise RuntimeError("No se encontró el bloque serial esperado en logger_weather.py")

text = text.replace(old, new)

p.write_text(text, encoding="utf-8")

print("OK: logger_weather.py sincronizado para tramas WSCSV")
print(f"Backup creado en: {backup}")
