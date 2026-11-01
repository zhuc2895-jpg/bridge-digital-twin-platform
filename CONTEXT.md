# Bridge Digital Twin Monitoring

Context for a bridge structural health monitoring platform that turns timestamped sensor readings into physical-threshold alerts and historical replay data.

## Language

**Sensor Reading**:
A timestamped measurement from one bridge sensor.
_Avoid_: sample, data point

**Known Sensor**:
A sensor with at least one Sensor Reading in the current process's monitoring store.
_Avoid_: online sensor when its latest reading is stale, configured sensor

**Online Sensor**:
A Known Sensor whose latest Sensor Reading is within the Online Sensor Freshness interval of the observing surface's reference time, whether shortly before or shortly after it; reports use their statistical end time, while live health and dashboards use the current time. A later future timestamp makes the sensor offline and time-invalid.
_Avoid_: any known sensor, active sensor

**Online Sensor Freshness**:
The provisional 60-second interval within which a Known Sensor's latest reading keeps it online around the observing surface's reference time; a reading exactly 60 seconds old or 60 seconds in the future is still online.
_Avoid_: alert cooldown, live frame staleness

**Time-Valid Sensor Reading**:
A Sensor Reading whose timestamp is no more than the Online Sensor Freshness interval after the reference time; later future timestamps are time-invalid.
_Avoid_: online reading, valid sample

**Sensor Connection State**:
Whether a Known Sensor is currently online or offline.
_Avoid_: physical state, alert level

**Sensor Physical State**:
The normal, yellow, orange, or red condition derived from a sensor's latest Time-Valid Sensor Reading and its Threshold Profile, or unknown when no time-valid reading exists; it is independent of connection state.
_Avoid_: connection state, alert state

**Cumulative Reading Count**:
The number of Sensor Readings ingested since the current process started, across all ingestion paths; a process restart resets it.
_Avoid_: online sensor count, period reading count

**Period Reading Count**:
The number of Sensor Readings whose timestamp falls within the report's inclusive statistical period, across all ingestion paths.
_Avoid_: cumulative reading count, live reading count

**Injected Reading**:
A Sensor Reading generated immediately for one specified sensor by applying a one-shot anomaly transform while advancing only that sensor's stream position.
_Avoid_: synthetic reading, queued injection

**Manual Anomaly Injection**:
A command that requests exactly one Injected Reading for a specified sensor and sends it through the normal monitoring chain.
_Avoid_: test anomaly, direct alert

**Physical Threshold**:
A positive limit assigned to one sensor type and one alert level.
_Avoid_: alarm limit, cutoff

**Threshold Profile**:
The yellow, orange, and red physical thresholds shared by every sensor of one type unless that sensor has a Sensor Threshold Override.
_Avoid_: one universal threshold set

**Sensor Threshold Override**:
A yellow, orange, and red physical threshold set for one specific sensor, taking precedence over its type's Threshold Profile when an engineering allowable value differs per measurement, such as cable acceleration versus deck acceleration.
_Avoid_: type-wide profile, runtime alert cooldown

**Threshold Units**:
Strain uses microstrain (µε), displacement uses millimetres (mm), acceleration uses metres per second squared (m/s²), and temperature uses degrees Celsius (°C).
_Avoid_: implicit units, mixed units

**Provisional Threshold Default**:
A physical threshold value used to keep the system runnable before an authoritative engineering source is available.
_Avoid_: SRS threshold, approved limit

**Alert**:
A retained record created when a sensor reading's absolute value reaches its highest matching physical threshold or an AI detector confirms an anomaly. Its sensor name and threshold are snapshots taken when the alert is created.
_Avoid_: event, notification

**Alert Value**:
The original signed sensor reading that caused an alert, even though threshold comparison uses its absolute value.
_Avoid_: absolute reading, normalized value

**Alert Source**:
The origin of an alert: `rule`, or one of `ai_stalwart`, `ai_gan_ae`, `ai_isolation_forest`, `ai_dual_confirm`, and `ai_feature_arbitration`.
_Avoid_: ml_* label, unprefixed detector name

**Alert Level**:
One of yellow, orange, or red, ordered from least to most severe.
_Avoid_: severity, priority

**Alert Event Time**:
The timestamp of the sensor reading that caused an alert; it is the clock used for cooldown and historical replay.
_Avoid_: detection time, arrival time

**Alert Cooldown**:
A ten-second period measured in alert event time during which another alert of the same level is not created for the same sensor, regardless of alert source; a reading exactly ten seconds later is outside the cooldown.
_Avoid_: debounce, mute window

**Retained Alert**:
An alert within the global 50,000-record storage limit; when capacity is exceeded, the alert with the oldest event time is evicted first.
_Avoid_: archived alert, active alert

**Recent Alert**:
One of the newest retained alerts by event time, with later detection order breaking same-time ties, regardless of whether its physical condition still exists.
_Avoid_: active alert, unresolved alert

**Alert ID**:
A globally unique UUIDv4 identifier for an alert across all sources, processes, and restarts.
_Avoid_: process-local ID, sequence number

**Alert Detection Order**:
The relative order in which alerts are created; later-created alerts sort first when multiple alerts share the same event time.
_Avoid_: alert timestamp, alert ID order

**Normal State**:
A sensor condition below its yellow physical threshold; green represents this state visually but is not an alert level.
_Avoid_: green alert

**Live Tick**:
The application-wide instant at which the current monitoring state is sampled and broadcast to subscribers, independent of WebSocket client connections.
_Avoid_: per-client tick, connection timer

**Live Frame**:
One `sensor_update` snapshot emitted by a Live Tick, with exactly one scheduled emission per second and a UTF-8 encoded size no greater than 10KB.
_Avoid_: per-upload frame, immediate update

**Live Eligible Sensor Reading**:
A Sensor Reading marked to participate in future Live Frames; backfill and non-live uploads are not Live Eligible.
_Avoid_: immediate reading, pushed reading

**Live Sensor Snapshot**:
The latest Live Eligible Sensor Reading for each sensor at one Live Tick, ordered by event time with stable tie-breaking and limited to the 32 most recent sensors.
_Avoid_: simulator-only batch, upload event batch

**Realtime Alert Projection**:
The bounded core representation of a Recent Alert produced by Live Eligible data; invalid numeric values are represented as null and marked invalid, while full alert evidence remains available through alert queries.
_Avoid_: full alert payload, detail-bearing alert, backfill alert

**Slow Client**:
A WebSocket subscriber that cannot accept a Live Frame within the latency budget or whose bounded queue is full.
_Avoid_: lagging client, backlogged subscriber

**Live Stream Loop**:
The single process-scoped cycle that advances simulation or ingestion and emits Live Frames.
_Avoid_: per-connection loop, per-client generator, cross-worker loop

### Vibration Benchmark

**Structural Condition**:
The intact, recovered, or damaged condition encoded in a Vibration Case label: `INT`, `RCV`, `DMG1`, `DMG2`, or `DMG3`.
_Avoid_: case count, damage class_

**Vibration Case**:
A named VBA test condition combining a structural condition with a speed label, such as `INT 40km` or `DMG1 40km`.
_Avoid_: class, damage label

**Vibration Recording**:
A time-indexed multichannel acceleration capture from one vibration case.
_Avoid_: waveform sample, row

**Acceleration Channel**:
One measured acceleration signal within a vibration recording.
_Avoid_: column, sensor (until a channel-to-sensor mapping is established)

**Intact Vibration Case**:
A Vibration Case whose structural condition is `INT`.
_Avoid_: baseline case, clean sample

**Recovery Vibration Case**:
A Vibration Case whose structural condition is `RCV`, treated as normal for evaluation.
_Avoid_: damaged case, repaired anomaly

**Damage Vibration Case**:
A Vibration Case whose structural condition is `DMG1`, `DMG2`, or `DMG3`.
_Avoid_: anomaly sample, failure case

**VBA Benchmark**:
An acceptance benchmark using the `VBA` variable from `Old_ADA_Bridge-damage_vibration_data.mat` and recording-level damage labels.
_Avoid_: validation dataset, training set

**Damage Label**:
A binary classification of a Vibration Recording as normal (`INT`, `RCV`) or damaged (`DMG1`, `DMG2`, `DMG3`).
_Avoid_: anomaly flag, alert label

### Simulation-Measurement Fusion

**Model Cognition**:
The degree to which an AI model recognizes a sample as belonging to its learned operating domain, derived from agreement among distinct sublearners.
_Avoid_: confidence, anomaly score

**Uncertainty Gate**:
A policy that downgrades or routes an AI result to arbitration when model cognition is low or sublearner disagreement is high, instead of allowing the result to directly create a high-severity alert.
_Avoid_: confidence threshold, cooldown

**Consensus Confidence**:
The combined reliability of an AI verdict after accounting for model votes, individual confidences, and model cognition.
_Avoid_: average confidence, model score

**Spatial Residual**:
The difference between a sensor reading and the value predicted for that sensor from other sensors at the same timestamp.
_Avoid_: prediction error, sensor noise

**Calibration Case**:
A versioned simulation or measurement scenario that pairs input features with a target load or structural response and declares its fidelity level.
_Avoid_: sample, data row

**Simulation-Measurement Compensation**:
A two-stage response estimate in which a simulation-based model supplies the baseline prediction and a measurement-based model corrects its bias.
_Avoid_: data mapping, simulation replacement

**Modal Coordinate**:
The contribution weight of one selected structural mode in a reconstructed deformation field.
_Avoid_: mode, coefficient

**Full-Field Deformation Inversion**:
Estimation of deformation across structural locations from sparse measurements using structural modes and sensor confidence.
_Avoid_: deformation prediction, shape interpolation

**Reconstruction Residual**:
The difference between a measured structural response and the response reconstructed from the selected deformation model.
_Avoid_: reconstruction error, alert value
