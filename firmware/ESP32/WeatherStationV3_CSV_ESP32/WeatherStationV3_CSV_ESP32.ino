/*
=========================================================
AtmosLink Research Platform
Firmware : WeatherStationV3_CSV_ESP32
Version  : 3.0
Station  : SJ01
Hardware : ESP32 + BME280 + Rain Gauge
Author   : Carlos Koo
=========================================================
*/

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <math.h>

#define STATION_ID "SJ01"

#define SDA_PIN   21
#define SCL_PIN   22
#define RAIN_PIN  27

#define BME280_ADDRESS 0x76

const float MM_PER_TIP = 0.2794;
const unsigned long SAMPLE_INTERVAL_MS = 5000;
const unsigned long DEBOUNCE_MS = 600;
const unsigned long BME_WARMUP_MS = 30000;

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

bool validBME(float t, float h, float p)
{
  if (!isfinite(t) || !isfinite(h) || !isfinite(p))
    return false;

  if (t < -30.0 || t > 60.0)
    return false;

  if (h < 0.0 || h > 100.0)
    return false;

  if (p < 500.0 || p > 1100.0)
    return false;

  return true;
}

bool readBMEStable(float &temperature, float &humidity, float &pressure)
{
  const int maxRetries = 5;

  for (int i = 0; i < maxRetries; i++)
  {
    float t = bme.readTemperature();
    float h = bme.readHumidity();
    float p = bme.readPressure() / 100.0F;

    if (validBME(t, h, p))
    {
      temperature = t;
      humidity = h;
      pressure = p;
      return true;
    }

    delay(150);
  }

  return false;
}

void setup()
{
  Serial.begin(115200);
  delay(2000);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

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

  bme.setSampling(
    Adafruit_BME280::MODE_NORMAL,
    Adafruit_BME280::SAMPLING_X2,
    Adafruit_BME280::SAMPLING_X16,
    Adafruit_BME280::SAMPLING_X1,
    Adafruit_BME280::FILTER_X16,
    Adafruit_BME280::STANDBY_MS_500
  );

  Serial.println("INFO,WEATHER_STATION_V3_CSV_READY");
  Serial.println("INFO,FORMAT,WSCSV,station_id,uptime_ms,temperature_c,humidity_pct,pressure_hpa,rain_tips,rain_mm");
}

void loop()
{
  unsigned long now = millis();

  if (now < BME_WARMUP_MS)
  {
    delay(500);
    return;
  }

  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS)
  {
    lastSampleTime = now;

    noInterrupts();
    unsigned long tips = rainTips;
    interrupts();

    float temperature = NAN;
    float humidity = NAN;
    float pressure = NAN;
    float rainMM = tips * MM_PER_TIP;

    bool ok = readBMEStable(temperature, humidity, pressure);

    if (!ok)
    {
      Serial.print("WARN,BME280_INVALID,");
      Serial.println(now);
      return;
    }

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
