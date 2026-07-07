from pathlib import Path

p = Path("weather_station/logger/logger_weather.py")
text = p.read_text(encoding="utf-8")

backup = p.with_suffix(".py.bak_accept_classic")
backup.write_text(text, encoding="utf-8")

old = '''                    # Descartar fragmentos o mensajes informativos.
                    # La trama válida del firmware V3 debe iniciar con WSCSV.
                    if not line.startswith("WSCSV"):
                        print("RX_DESCARTADO:", line)
                        continue

                    print("RX:", line)
'''

new = '''                    # Descartar mensajes informativos del firmware.
                    if line.startswith("INFO") or line.startswith("ERROR") or line.startswith("WARN"):
                        print("RX_DESCARTADO:", line)
                        continue

                    # Aceptar formato clásico AtmosLink y formato WSCSV.
                    print("RX:", line)
'''

if old not in text:
    raise RuntimeError("No se encontró el bloque WSCSV en logger_weather.py")

text = text.replace(old, new)

p.write_text(text, encoding="utf-8")

print("OK: logger_weather.py ahora acepta formato clásico AtmosLink")
print(f"Backup creado en: {backup}")
