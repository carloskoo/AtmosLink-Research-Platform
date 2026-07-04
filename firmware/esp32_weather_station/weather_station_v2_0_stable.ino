/*
=========================================================
ESTACIÓN METEOROLÓGICA V2 CSV - STABLE
ESP32 + BME280 + Bucket Rainfall
Estación: SJ01 - Cerro San José
=========================================================
*/

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>

#define STATION_ID "SJ01"

#define SDA_PIN   21
#define SCL_PIN   22
#define RAIN_PIN  27

#define BME280_ADDRESS 0x76

const float MM_PER_TIP = 0.2794;
const unsigned long SAMPLE_INTERVAL_MS = 5000;
const unsigned long DEBOUNCE_MS = 200;

Adafruit_BME280 bme;

volatile unsigned long rainTips = 0;
volatile unsigned long lastTipTime = 0;

unsigned long lastSampleTime = 0;

void IRAM_ATTR rainInterrupt()
{
  unsigned long now = millis();

  if (now - lastTipTime > DEBOUNCE_MS)
  {
    rainTips++;
    lastTipTime = now;
  }
}

void setup()
{
  Serial.begin(115200);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);

  pinMode(RAIN_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RAIN_PIN), rainInterrupt, FALLING);

  if (!bme.begin(BME280_ADDRESS))
  {
    Serial.println("ERROR,BME280_NOT_FOUND");

    while (true)
    {
      delay(1000);
    }
  }

  Serial.println("INFO,WEATHER_STATION_V2_CSV_READY");
  Serial.println("INFO,FORMAT,WSCSV,station_id,uptime_ms,temperature_c,humidity_pct,pressure_hpa,rain_tips,rain_mm");
}

void loop()
{
  unsigned long now = millis();

  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS)
  {
    lastSampleTime = now;

    noInterrupts();
    unsigned long tips = rainTips;
    interrupts();

    float temperature = bme.readTemperature();
    float humidity = bme.readHumidity();
    float pressure = bme.readPressure() / 100.0F;
    float rainMM = tips * MM_PER_TIP;

    Serial.print("WSCSV,");
    Serial.print(STATION_ID);
    Serial.print(",");
    Serial.print(now);
    Serial.print(",");
    Serial.print(temperature, 2);
    Serial.print(",");
    Serial.print(humidity, 2);
    Serial.print(",");
    Serial.print(pressure, 2);
    Serial.print(",");
    Serial.print(tips);
    Serial.print(",");
    Serial.println(rainMM, 3);
  }
}
