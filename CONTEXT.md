# Bridge Digital Twin Monitoring

Context for a bridge structural health monitoring platform that turns timestamped sensor readings into physical-threshold alerts and historical replay data.

## Language

**Sensor Reading**:
A timestamped measurement from one bridge sensor.
_Avoid_: sample, data point

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
The yellow, orange, and red physical thresholds shared by every sensor of one type.
_Avoid_: per-sensor threshold set

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
