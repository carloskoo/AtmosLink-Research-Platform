import unittest

from weather_station.propagation.atmospheric_inputs import (
    water_vapour_density_g_m3,
)
from weather_station.propagation.iturpy_adapter import (
    assert_supported_baseline_versions,
    gaseous_attenuation_terrestrial,
    get_model_versions,
    rain_specific_attenuation,
)


class ITURpyAdapterTest(unittest.TestCase):

    def test_model_versions(self):
        versions = get_model_versions()

        self.assertEqual(versions.itu530, 17)
        self.assertEqual(versions.itu676, 12)
        self.assertEqual(versions.itu838, 3)

        assert_supported_baseline_versions()

    def test_zero_rain(self):
        result = rain_specific_attenuation(
            rain_rate_mm_h=0.0,
            frequency_ghz=5.8,
            elevation_angle_deg=0.0,
            polarization_tilt_deg=0.0,
        )

        self.assertAlmostEqual(
            result.specific_attenuation_db_km,
            0.0,
            places=12,
        )

    def test_rain_increases_attenuation(self):
        low = rain_specific_attenuation(
            rain_rate_mm_h=5.0,
            frequency_ghz=5.8,
            elevation_angle_deg=0.0,
            polarization_tilt_deg=0.0,
        )

        high = rain_specific_attenuation(
            rain_rate_mm_h=50.0,
            frequency_ghz=5.8,
            elevation_angle_deg=0.0,
            polarization_tilt_deg=0.0,
        )

        self.assertGreater(
            high.specific_attenuation_db_km,
            low.specific_attenuation_db_km,
        )

    def test_water_vapour_density(self):
        rho = water_vapour_density_g_m3(
            temperature_c=13.9,
            relative_humidity_pct=81.62,
        )

        self.assertGreater(rho, 0.0)
        self.assertLess(rho, 30.0)

    def test_gaseous_attenuation_is_non_negative(self):
        rho = water_vapour_density_g_m3(
            temperature_c=13.9,
            relative_humidity_pct=81.62,
        )

        result = gaseous_attenuation_terrestrial(
            path_distance_km=12.0,
            frequency_ghz=5.8,
            elevation_angle_deg=0.0,
            water_vapour_density_g_m3=rho,
            pressure_hpa=743.65,
            temperature_k=13.9 + 273.15,
            mode="exact",
        )

        self.assertGreaterEqual(result.attenuation_db, 0.0)


if __name__ == "__main__":
    unittest.main()
