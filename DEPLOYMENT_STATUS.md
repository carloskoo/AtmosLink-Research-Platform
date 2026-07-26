# AtmosLink deployment status

## Current stage

Pre-deployment software verification.

## Available infrastructure

- Cuñacales climatic station: installed or under local operation.
- San José climatic station: pending deployment.
- Intermediate climatic station: pending deployment.
- Cuñacales–San José radio link: pending installation or reactivation.
- RF telemetry used in current propagation-validation tests: synthetic.

## Valid interpretation of current results

Current RECV metrics and figures validate the software pipeline only.
They must not be interpreted as experimental propagation results.

## Synthetic identifiers

- Link ID: CU01_SJ01_58_SYNTHETIC
- Model version: recv-1.1.0-synthetic

## Reserved field identifiers

- Link ID: CU01_SJ01_58_FIELD
- Model version: recv-1.1.0-field

## Field activation checklist

- Install and align the radio link.
- Confirm stable AP–SM connectivity.
- Synchronize clocks at all nodes.
- Confirm Cuñacales meteorological acquisition.
- Install and validate San José meteorological acquisition.
- Install and validate the intermediate station, if retained.
- Verify RF telemetry collection.
- Verify common timestamps and time zone.
- Record dry baseline periods.
- Accumulate independent real rain events.
- Run field RECV only after quality-control checks.
