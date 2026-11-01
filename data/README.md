# Data Layout

- `samples/`: small committed examples for API/manual testing.
- `validation/`: committed validation data used for demos and benchmark setup.
- `external/`: external raw datasets. This directory is ignored by Git unless a specific derived artifact is promoted with checksum and provenance.

Do not treat sample or generated validation data as field measurements. Use `benchmarks/vba/` for the acceptance benchmark.
