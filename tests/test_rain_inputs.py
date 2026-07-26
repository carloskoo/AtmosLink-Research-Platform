import unittest
from datetime import datetime, timedelta, timezone

from weather_station.propagation.rain_inputs import (
    RainIntervalInput,
    RainProcessorConfiguration,
    RainQualityFlag,
    equivalent_rain_rate_mm_h,
    precipitation_from_pulses,
    process_pulse_interval,
    process_rain_interval,
)


class RainInputProcessorTest(unittest.TestCase):

    def setUp(self):
        self.start = datetime(
            2026,
            7,
            26,
            10,
            0,
            0,
            tzinfo=timezone.utc,
        )
        self.end = self.start + timedelta(seconds=60)

    def test_precipitation_from_one_pulse(self):
        value = precipitation_from_pulses(
            pulse_count=1,
            bucket_depth_mm=0.279,
        )

        self.assertAlmostEqual(value, 0.279, places=12)

    def test_one_pulse_in_one_minute(self):
        result = process_pulse_interval(
            timestamp_start=self.start,
            timestamp_end=self.end,
            pulse_count=1,
            bucket_depth_mm=0.279,
        )

        self.assertTrue(result.quality_valid)
        self.assertEqual(result.quality_flag, RainQualityFlag.VALID)
        self.assertAlmostEqual(result.precipitation_mm, 0.279)
        self.assertAlmostEqual(result.rain_rate_mm_h, 16.74)
        self.assertTrue(result.is_raining)

    def test_zero_pulses_is_valid_zero_rain(self):
        result = process_pulse_interval(
            timestamp_start=self.start,
            timestamp_end=self.end,
            pulse_count=0,
            bucket_depth_mm=0.279,
        )

        self.assertTrue(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.ZERO_RAIN,
        )
        self.assertEqual(result.rain_rate_mm_h, 0.0)
        self.assertFalse(result.is_raining)

    def test_equivalent_rate_uses_actual_interval(self):
        value = equivalent_rain_rate_mm_h(
            precipitation_mm=0.279,
            interval_seconds=90.0,
        )

        self.assertAlmostEqual(value, 11.16)

    def test_missing_precipitation(self):
        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=self.start,
                timestamp_end=self.end,
                precipitation_mm=None,
                source_field="rain_1min_mm",
            )
        )

        self.assertFalse(result.quality_valid)
        self.assertIsNone(result.rain_rate_mm_h)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.MISSING_PRECIPITATION,
        )

    def test_negative_precipitation(self):
        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=self.start,
                timestamp_end=self.end,
                precipitation_mm=-0.279,
            )
        )

        self.assertFalse(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.NEGATIVE_PRECIPITATION,
        )

    def test_duplicate_timestamp(self):
        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=self.start,
                timestamp_end=self.start,
                precipitation_mm=0.279,
            )
        )

        self.assertFalse(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.DUPLICATE_TIMESTAMP,
        )

    def test_interval_too_short(self):
        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=self.start,
                timestamp_end=self.start + timedelta(seconds=10),
                precipitation_mm=0.279,
            )
        )

        self.assertFalse(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.INTERVAL_TOO_SHORT,
        )

    def test_interval_too_long(self):
        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=self.start,
                timestamp_end=self.start + timedelta(seconds=300),
                precipitation_mm=0.279,
            )
        )

        self.assertFalse(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.INTERVAL_TOO_LONG,
        )

    def test_extreme_rate_is_flagged(self):
        config = RainProcessorConfiguration(
            minimum_interval_seconds=30,
            maximum_interval_seconds=180,
            maximum_rain_rate_mm_h=100,
        )

        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=self.start,
                timestamp_end=self.end,
                precipitation_mm=2.0,
            ),
            configuration=config,
        )

        self.assertAlmostEqual(result.rain_rate_mm_h, 120.0)
        self.assertFalse(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.RATE_ABOVE_LIMIT,
        )

    def test_missing_timestamp(self):
        result = process_rain_interval(
            RainIntervalInput(
                timestamp_start=None,
                timestamp_end=self.end,
                precipitation_mm=0.279,
            )
        )

        self.assertFalse(result.quality_valid)
        self.assertEqual(
            result.quality_flag,
            RainQualityFlag.MISSING_TIMESTAMP,
        )


if __name__ == "__main__":
    unittest.main()
