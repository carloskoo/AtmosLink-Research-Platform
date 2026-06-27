#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include "DFRobot_RainfallSensor.h"

#define SDA_PIN 8
#define SCL_PIN 9
#define BME280_ADDR 0x76

const unsigned long SAMPLE_INTERVAL_MS = 5000;
const unsigned long LOG_INTERVAL_MS    = 60000;

Adafruit_BME280 bme;
DFRobot_RainfallSensor_I2C rain(&Wire);

unsigned long lastSample = 0;
unsigned long lastLog = 0;

float tempSum = 0.0;
float humSum = 0.0;
float presSum = 0.0;

float tempMin = 999.0;
float tempMax = -999.0;
float humMin = 999.0;
float humMax = -999.0;

int sampleCount = 0;

float lastRainTotal = 0.0;
uint32_t lastPulses = 0;

bool bmeOK = false;
bool rainOK = false;

bool isValidBMEReading(float temp, float hum, float pres) {
  if (isnan(temp) || isnan(hum) || isnan(pres)) return false;
  if (temp < -30.0 || temp > 60.0) return false;
  if (hum < 0.0 || hum > 100.0) return false;
  if (pres < 500.0 || pres > 1100.0) return false;
  return true;
}

float calcDewPoint(float tempC, float humPct) {
  const float a = 17.27;
  const float b = 237.7;

  if (isnan(tempC) || isnan(humPct)) return NAN;
  if (humPct <= 0.0 || humPct > 100.0) return NAN;

  float gamma = (a * tempC) / (b + tempC) + log(humPct / 100.0);
  return (b * gamma) / (a - gamma);
}

float calcSaturationVaporPressure(float tempC) {
  if (isnan(tempC)) return NAN;
  if (tempC < -40.0 || tempC > 80.0) return NAN;

  return 6.112 * exp((17.67 * tempC) / (tempC + 243.5));
}

float calcVaporPressure(float tempC, float humPct) {
  if (isnan(tempC) || isnan(humPct)) return NAN;
  if (humPct < 0.0 || humPct > 100.0) return NAN;

  float es = calcSaturationVaporPressure(tempC);
  if (isnan(es)) return NAN;

  return (humPct / 100.0) * es;
}

void resetStats() {
  tempSum = 0.0;
  humSum = 0.0;
  presSum = 0.0;

  tempMin = 999.0;
  tempMax = -999.0;
  humMin = 999.0;
  humMax = -999.0;

  sampleCount = 0;
}

void printHeader() {
  Serial.println("ESTACION OK");
  Serial.println("t_s,temp_avg_C,temp_min_C,temp_max_C,hum_avg_pct,hum_min_pct,hum_max_pct,pres_avg_hPa,dew_point_C,vapor_pressure_hPa,rain_1min_mm,rain_1h_mm,rain_total_mm,pulses_delta,pulses_total,bme_ok,rain_ok");
}

void setup() {
  Serial.begin(115200);
  delay(2000);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  delay(500);

  bmeOK = bme.begin(BME280_ADDR, &Wire);

  if (bmeOK) {
    bme.setSampling(
      Adafruit_BME280::MODE_NORMAL,
      Adafruit_BME280::SAMPLING_X2,
      Adafruit_BME280::SAMPLING_X16,
      Adafruit_BME280::SAMPLING_X1,
      Adafruit_BME280::FILTER_X16,
      Adafruit_BME280::STANDBY_MS_500
    );
  } else {
    Serial.println("ERROR: BME280 no encontrado en 0x76");
    Serial.println("Revise SDA=GPIO8, SCL=GPIO9, VCC=3.3V y GND.");
  }

  rainOK = rain.begin();

  if (!rainOK) {
    Serial.println("ERROR: Rainfall no encontrado en I2C");
    Serial.println("Revise conexion del pluviometro.");
  }

  delay(1000);

  if (rainOK) {
    lastRainTotal = rain.getRainfall();
    if (isnan(lastRainTotal) || lastRainTotal < 0.0) {
      lastRainTotal = 0.0;
    }

    lastPulses = rain.getRawData();
  }

  printHeader();

  resetStats();

  lastSample = millis() - SAMPLE_INTERVAL_MS;
  lastLog = millis();
}

void loop() {
  unsigned long now = millis();

  if (now - lastSample >= SAMPLE_INTERVAL_MS) {
    lastSample = now;

    if (bmeOK) {
      float temp = bme.readTemperature();
      float hum = bme.readHumidity();
      float pres = bme.readPressure() / 100.0F;

      if (isValidBMEReading(temp, hum, pres)) {
        tempSum += temp;
        humSum += hum;
        presSum += pres;

        if (temp < tempMin) tempMin = temp;
        if (temp > tempMax) tempMax = temp;

        if (hum < humMin) humMin = hum;
        if (hum > humMax) humMax = hum;

        sampleCount++;
      }
    }
  }

  if (now - lastLog >= LOG_INTERVAL_MS) {
    lastLog = now;

    float tempAvg = NAN;
    float humAvg = NAN;
    float presAvg = NAN;
    float dewPoint = NAN;
    float vaporPressure = NAN;

    int bmeValid = 0;

    if (sampleCount > 0) {
      tempAvg = tempSum / sampleCount;
      humAvg = humSum / sampleCount;
      presAvg = presSum / sampleCount;

      if (isValidBMEReading(tempAvg, humAvg, presAvg)) {
        dewPoint = calcDewPoint(tempAvg, humAvg);
        vaporPressure = calcVaporPressure(tempAvg, humAvg);
        bmeValid = 1;
      }
    }

    float rainTotal = 0.0;
    float rain1h = 0.0;
    float rain1min = 0.0;

    uint32_t pulsesTotal = 0;
    uint32_t pulsesDelta = 0;

    int rainValid = 0;

    if (rainOK) {
      rainTotal = rain.getRainfall();
      rain1h = rain.getRainfall(1);
      pulsesTotal = rain.getRawData();

      if (isnan(rainTotal) || rainTotal < 0.0) rainTotal = 0.0;
      if (isnan(rain1h) || rain1h < 0.0) rain1h = 0.0;

      rain1min = rainTotal - lastRainTotal;

      if (isnan(rain1min) || rain1min < 0.0) {
        rain1min = 0.0;
      }

      if (pulsesTotal >= lastPulses) {
        pulsesDelta = pulsesTotal - lastPulses;
      } else {
        pulsesDelta = 0;
      }

      lastRainTotal = rainTotal;
      lastPulses = pulsesTotal;

      rainValid = 1;
    }

    Serial.print(now / 1000);
    Serial.print(",");

    Serial.print(tempAvg, 2);
    Serial.print(",");
    Serial.print(sampleCount > 0 ? tempMin : NAN, 2);
    Serial.print(",");
    Serial.print(sampleCount > 0 ? tempMax : NAN, 2);
    Serial.print(",");

    Serial.print(humAvg, 2);
    Serial.print(",");
    Serial.print(sampleCount > 0 ? humMin : NAN, 2);
    Serial.print(",");
    Serial.print(sampleCount > 0 ? humMax : NAN, 2);
    Serial.print(",");

    Serial.print(presAvg, 2);
    Serial.print(",");
    Serial.print(dewPoint, 2);
    Serial.print(",");
    Serial.print(vaporPressure, 2);
    Serial.print(",");

    Serial.print(rain1min, 2);
    Serial.print(",");
    Serial.print(rain1h, 2);
    Serial.print(",");
    Serial.print(rainTotal, 2);
    Serial.print(",");
    Serial.print(pulsesDelta);
    Serial.print(",");
    Serial.print(pulsesTotal);
    Serial.print(",");

    Serial.print(bmeValid);
    Serial.print(",");
    Serial.println(rainValid);

    resetStats();
  }
}
