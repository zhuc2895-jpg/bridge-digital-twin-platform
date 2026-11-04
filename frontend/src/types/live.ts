export interface SensorReading {
  sensor_id: string
  name: string
  type: string
  value: number
  timestamp: number
  physical_state: PhysicalState
  connection_state: ConnectionState
}

export type PhysicalState = 'normal' | 'yellow' | 'orange' | 'red' | 'unknown'
export type ConnectionState = 'online' | 'offline'

export type AlertLevel = 'yellow' | 'orange' | 'red'
export type AlertSource =
  | 'rule'
  | 'ai_stalwart'
  | 'ai_gan_ae'
  | 'ai_isolation_forest'
  | 'ai_dual_confirm'
  | 'ai_feature_arbitration'

export interface Alert {
  id: string
  sensor_id: string
  sensor_name: string
  level: AlertLevel
  message: string
  value: number | null
  threshold: number | null
  source: AlertSource
  timestamp: number | null
  invalid: boolean
}

export interface Stats {
  total_readings: number
  sensor_count: number
  online_sensor_count: number
  retained_alerts: number
  throughput: number
  uptime_seconds: number
}

export interface PressureGrid {
  nx: number
  nz: number
  x_min: number
  x_max: number
  z_min: number
  z_max: number
}

export interface PressurePoint {
  sensor_id: string
  x: number
  z: number
  ratio: number
  value: number
  physical_state: PhysicalState
}

export interface PressureField {
  type: 'pressure_update'
  version: number
  generated_at: number
  unit: string
  metric: string
  grid: PressureGrid
  values: number[]
  max: number
  max_level: PhysicalState
  max_sensor_id: string | null
  coverage: number
  points: PressurePoint[]
}

export interface BridgeModel {
  model_id: string
  name: string
  format: 'glb' | 'gltf'
  size_bytes: number
  original_filename: string
  created_at: string
  active: boolean
  file_url: string
  media_type: string
  profile_revision: number
  profile_source: 'bundled' | 'explicit' | 'inferred'
  profile_url: string
}

export interface ActiveBridgeModel {
  active: BridgeModel | null
  source: 'imported' | 'bundled'
  file_url: string
  default_url: string
  profile_url: string
  profile_revision: number
  profile_source: 'bundled' | 'explicit' | 'inferred'
}

export interface SceneDeckBounds {
  min_x: number
  max_x: number
  min_y: number
  max_y: number
  min_z: number
  max_z: number
}

export interface SceneModelTransform {
  translation: [number, number, number]
  rotation: [number, number, number, number]
  scale: [number, number, number]
  source_unit_scale: number
}

export interface SceneSensorAnchor {
  position: [number, number, number]
  role?: string
}

export interface BridgeSceneProfile {
  schema_version: number
  profile_id: string
  revision: number
  source: 'bundled' | 'explicit' | 'inferred'
  coordinate_frame: {
    handedness: 'right'
    units: 'm'
    up: 'Y'
    longitudinal: 'X'
    transverse: 'Z'
  }
  model_transform: SceneModelTransform
  deck_bounds: SceneDeckBounds
  sensor_anchors: Record<string, SceneSensorAnchor>
  measurement_roles: Record<string, string>
  display: Record<string, unknown>
}
