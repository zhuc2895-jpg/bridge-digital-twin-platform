import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SensorData, Alert, Stats } from '../composables/useWebSocket'

/**
 * 桥梁状态管理 (Pinia)
 * 全局共享的传感器数据、告警、系统状态
 */

export const useBridgeStore = defineStore('bridge', () => {
  // 传感器数据
  const sensorData = ref<SensorData[]>([])
  const alerts = ref<Alert[]>([])
  const stats = ref<Stats | null>(null)

  // 连接状态
  const connected = ref(false)
  const lastUpdate = ref<number>(0)

  // 3D 视图状态
  const selectedSensor = ref<string | null>(null)
  const cameraMode = ref<'free' | 'orbit' | 'top' | 'front'>('orbit')
  const showSensorLabels = ref(true)
  const highlightAnomalies = ref(true)

  // 数据看板状态
  const chartTimeRange = ref<number>(60) // 默认60分钟
  const selectedChartSensor = ref<string>('S01')

  // 仿真控制
  const simulatorRunning = ref(false)

  // 更新传感器数据
  function updateSensorData(data: SensorData[]) {
    sensorData.value = data
    lastUpdate.value = Date.now()
  }

  // 更新告警
  function updateAlerts(newAlerts: Alert[]) {
    alerts.value = newAlerts
  }

  // 更新统计
  function updateStats(newStats: Stats) {
    stats.value = newStats
  }

  // 设置连接状态
  function setConnected(status: boolean) {
    connected.value = status
  }

  // 选中传感器
  function selectSensor(sensorId: string | null) {
    selectedSensor.value = sensorId
  }

  // 获取告警数量（按级别）
  const alertCountByLevel = computed(() => {
    const count: Record<string, number> = { red: 0, orange: 0, yellow: 0 }
    alerts.value.forEach(a => {
      if (count[a.level] !== undefined) count[a.level]++
    })
    return count
  })

  // 获取最新告警（前5条）
  const latestAlerts = computed(() => {
    return alerts.value.slice(-5).reverse()
  })

  // 获取应变传感器数据
  const strainSensors = computed(() =>
    sensorData.value.filter(s => s.type === 'strain')
  )

  return {
    sensorData,
    alerts,
    stats,
    connected,
    lastUpdate,
    selectedSensor,
    cameraMode,
    showSensorLabels,
    highlightAnomalies,
    chartTimeRange,
    selectedChartSensor,
    simulatorRunning,
    alertCountByLevel,
    latestAlerts,
    strainSensors,
    updateSensorData,
    updateAlerts,
    updateStats,
    setConnected,
    selectSensor
  }
})
