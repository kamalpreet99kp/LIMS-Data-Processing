# Ex345_calibrated-Test.csv Validation Report

This report records a direct run of core loading/detection/matching logic using `Ex345_calibrated-Test.csv` fetched from repository `main`.

## Dataset stats
- Rows: 4096
- Mass range: 0.488761213 to 258.6664814
- Counts range: 37.0 to 1023.0

## Peak detection sample
Using defaults:
- Threshold: 365
- Prominence: 50
- Distance: 5

Detected peaks: 13
First 10 peak masses:
- 11.8961
- 23.8550
- 26.8422
- 31.8862
- 38.8484
- 51.8161
- 53.7814
- 54.8334
- 55.7833
- 62.8397

## Isotope matching checks (exact mode, tolerance 0.3)
- 106.8950 -> Ag-107
- 108.8458 -> Ag-109
- 55.9349 -> Fe-56
- 62.9296 -> Cu-63
- 64.9278 -> Cu-65
- 31.9721 -> S-32

## Notes
- Core matching logic resolves Ag and Fe targets successfully with tolerance 0.3.
- GUI runtime could not be fully executed in this CI container due system library dependency (`libGL.so.1`).
