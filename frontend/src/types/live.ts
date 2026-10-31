export interface SensorData {
  sensor_id: string
  name: string
  type: string
  position: string
  value: number
  timestamp: number
}

export interface Alert {
  id: string
  sensor_id: string
  sensor_name: string
  level: string
  message: string
  value: number | null
  threshold: number | null
  source: string
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
