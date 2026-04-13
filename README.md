# LIMS-Data-Processing
Processing the ".dat" files from LIMS Analysis

## TOF-LIMS CSV Peak Pipeline

This repository also includes `tof_lims_peak_pipeline.py` for the next workflow stage:

1. Read a spectrum CSV.
2. Detect mass/intensity columns.
3. Detect peaks (`scipy.signal.find_peaks`).
4. Label peaks (`mass` mode or `element` mode).
5. Export peak table CSV and labeled plot PNG.

### Run

```bash
python tof_lims_peak_pipeline.py your_spectrum.csv --label-mode element
```

 codex/locate-dat-to-csv.py-script-05h1bd
### Install compatible dependencies (important)

If you see SciPy / NumPy errors like:
- `A NumPy version >=1.19.5 and <1.27.0 is required...`
- `AttributeError: _ARRAY_API not found`
- `ImportError: numpy.core.multiarray failed to import`

install pinned versions:

```bash
python -m pip install -r requirements-tof-lims.txt
```

On Windows, if you have multiple Python executables, use the same one as PyCharm:

```bash
py -3.9 -m pip install -r requirements-tof-lims.txt
```

 main
### Key tuning parameters

You can tune detection from command line:

```bash
python tof_lims_peak_pipeline.py your_spectrum.csv \
  --prominence 150 \
  --distance 6 \
  --match-tolerance 0.3
```

Or edit defaults at the top of the script:
- `PEAK_MIN_HEIGHT`
- `PEAK_MIN_PROMINENCE`
- `PEAK_MIN_DISTANCE`
- `MASS_MATCH_TOLERANCE`
- `REFERENCE_MASSES` (element/isotope lookup table)
