export interface SensorReading {
  sensor_id: string
  name: string
  type: string
  position: string
  value: number
  timestamp: number
}

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
  retained_alerts: number
  throughput: number
  uptime_seconds: number
}
