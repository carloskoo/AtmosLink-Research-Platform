# AtmosLink RECV scientific validation summary

- Run ID: 1
- Link: CU01_SJ01_58_TEST
- Model version: recv-1.1.0
- Independent rain events: 3
- Validation observations: 82

## Pooled validation results

- Physical model MAE: 2.497 dB
- Calibrated model MAE: 0.585 dB
- MAE reduction: 76.55%

- Physical model RMSE: 3.262 dB
- Calibrated model RMSE: 0.676 dB
- RMSE reduction: 79.28%

- Physical model bias: 2.412 dB
- Calibrated model bias: -0.335 dB

- Physical model R²: -17.263
- Calibrated model R²: 0.216

## Rain-residual relationship

- Pearson correlation between rain rate and physical-model residual: 0.954
- Pearson correlation between rain rate and calibrated-model residual: -0.398

## Inter-event behavior

- Event 1: n=25, α=0.3158, MAE 1.070 → 0.423 dB, change=60.50%.
- Event 2: n=45, α=0.1433, MAE 3.761 → 0.591 dB, change=84.28%.
- Event 3: n=12, α=0.2161, MAE 0.727 → 0.903 dB, change=-24.16%.

## Scientific interpretation

The event-based calibration reduced the pooled prediction error relative to the unscaled physical rain-attenuation model. The estimated rain-scale factor varied among events, indicating that it should be interpreted as an effective event-dependent parameter rather than a universal propagation constant.

Calibration did not improve every independent event. Negative improvement was observed in event(s): 3. This result must be reported because it reflects inter-event variability and prevents overstatement of the model's generalization.