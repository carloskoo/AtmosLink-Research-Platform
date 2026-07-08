/*
=========================================================
AtmosLink Research Platform
Firmware : WeatherStationV3_2_RobustRain_AtmosLink
Version  : 3.2
Station  : SJ01
Hardware : ESP32 + BME280 + Rain Gauge Direct GPIO
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

const unsigned long SAMPLE_INTERVAL_MS = 60000;
const unsigned long READ_INTERVAL_MS   = 5000;
const unsigned long BME_WARMUP_MS      = 30000;

const unsigned long RAIN_POLL_MS       = 20;
const unsigned long RAIN_STABLE_MS     = 80;
const unsigned long RAIN_MIN_TIP_MS    = 2000;

Adafruit_BME280 bme;

unsigned long rainTipsTotal = 0;
unsigned long lastTipsTotal = 0;
float rainTotalMM = 0.0;

int rainRawLast = HIGH;
int rainStableState = HIGH;
int rainStableLast = HIGH;

unsigned long rainRawChangedAt = 0;
unsigned long lastRainPollTime = 0;
unsigned long lastAcceptedTipTime = 0;

unsigned long lastSampleTime = 0;
unsigned long lastReadTime = 0;

float tempSum = 0.0;
float humSum = 0.0;
float presSum = 0.0;

float tempMin = 999.0;
float tempMax = -999.0;
float humMin = 999.0;
float humMax = -999.0;

int sampleCount = 0;

void pollRainGauge()
{
  unsigned long now = millis();

  if (now - lastRainPollTime < RAIN_POLL_MS)
    return;

  lastRainPollTime = now;

  int raw = digitalRead(RAIN_PIN);

  if (raw != rainRawLast)
  {
    rainRawLast = raw;
    rainRawChangedAt = now;
  }

  if ((now - rainRawChangedAt) >= RAIN_STABLE_MS)
  {
    if (raw != rainStableState)
    {
      rainStableLast = rainStableState;
      rainStableState = raw;

      if (rainStableLast == HIGH && rainStableState == LOW)
      {
        if (now - lastAcceptedTipTime >= RAIN_MIN_TIP_MS)
        {
          rainTipsTotal++;
          lastAcceptedTipTime = now;
        }
      }
    }
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

float dewPointC(float temperature, float humidity)
{
  if (humidity <= 0.0)
    return NAN;

  const float a = 17.27;
  const float b = 237.7;

  float alpha = ((a * temperature) / (b + temperature)) + log(humidity / 100.0);
  return (b * alpha) / (a - alpha);
}

float vaporPressureHpa(float temperature, float humidity)
{
  float es = 6.112 * exp((17.67 * temperature) / (temperature + 243.5));
  return es * humidity / 100.0;
}

void resetWindow()
{
  tempSum = 0.0;
  humSum = 0.0;
  presSum = 0.0;

  tempMin = 999.0;
  tempMax = -999.0;
  humMin = 999.0;
  humMax = -999.0;

  sampleCount = 0;
}

void setup()
{
  Serial.begin(115200);
  delay(2000);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  pinMode(RAIN_PIN, INPUT_PULLUP);

  rainRawLast = digitalRead(RAIN_PIN);
  rainStableState = rainRawLast;
  rainStableLast = rainRawLast;
  rainRawChangedAt = millis();

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

  resetWindow();

  Serial.println("INFO,WEATHER_STATION_V3_2_ROBUST_RAIN_ATMOSLINK_READY");
  Serial.println("INFO,FORMAT,t_s,temp_avg,temp_min,temp_max,hum_avg,hum_min,hum_max,pres_avg,dew_point,vapor_pressure,rain_1min,rain_1h,rain_total,pulses_delta,pulses_total,bme_ok,rain_ok");
}

void loop()
{
  unsigned long now = millis();

  pollRainGauge();

  if (now < BME_WARMUP_MS)
  {
    delay(10);
    return;
  }

  if (now - lastReadTime >= READ_INTERVAL_MS)
  {
    lastReadTime = now;

    float temperature = NAN;
    float humidity = NAN;
    float pressure = NAN;

    bool ok = readBMEStable(temperature, humidity, pressure);

    if (ok)
    {
      tempSum += temperature;
      humSum += humidity;
      presSum += pressure;

      if (temperature < tempMin) tempMin = temperature;
      if (temperature > tempMax) tempMax = temperature;
      if (humidity < humMin) humMin = humidity;
      if (humidity > humMax) humMax = humidity;

      sampleCount++;
    }
  }

  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS)
  {
    lastSampleTime = now;

    unsigned long tipsTotal = rainTipsTotal;
    unsigned long tipsDelta = tipsTotal - lastTipsTotal;
    lastTipsTotal = tipsTotal;

    float rain1min = tipsDelta * MM_PER_TIP;
    rainTotalMM = tipsTotal * MM_PER_TIP;

    int bmeOk = 0;
    int rainOk = 1;

    float tempAvg = NAN;
    float humAvg = NAN;
    float presAvg = NAN;
    float dewPoint = NAN;
    float vaporPressure = NAN;

    if (sampleCount > 0)
    {
      tempAvg = tempSum / sampleCount;
      humAvg = humSum / sampleCount;
      presAvg = presSum / sampleCount;

      dewPoint = dewPointC(tempAvg, humAvg);
      vaporPressure = vaporPressureHpa(tempAvg, humAvg);

      bmeOk = 1;
    }

    Serial.print(now / 1000);
    Serial.print(",");
    Serial.print(tempAvg, 2);
    Serial.print(",");
    Serial.print(tempMin, 2);
    Serial.print(",");
    Serial.print(tempMax, 2);
    Serial.print(",");
    Serial.print(humAvg, 2);
    Serial.print(",");
    Serial.print(humMin, 2);
    Serial.print(",");
    Serial.print(humMax, 2);
    Serial.print(",");
    Serial.print(presAvg, 2);
    Serial.print(",");
    Serial.print(dewPoint, 2);
    Serial.print(",");
    Serial.print(vaporPressure, 2);
    Serial.print(",");
    Serial.print(rain1min, 2);
    Serial.print(",");
    Serial.print(rain1min, 2);
    Serial.print(",");
    Serial.print(rainTotalMM, 2);
    Serial.print(",");
    Serial.print(tipsDelta);
    Serial.print(",");
    Serial.print(tipsTotal);
    Serial.print(",");
    Serial.print(bmeOk);
    Serial.print(",");
    Serial.println(rainOk);

    resetWindow();
  }
}
