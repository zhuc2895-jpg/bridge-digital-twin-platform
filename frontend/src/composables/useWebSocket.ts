import { ref, onMounted, onUnmounted } from 'vue'

/**
 * WebSocket 实时数据连接
 * 连接后端 ws://localhost:8000/ws/live
 * 接收传感器数据、告警信息、统计信息
 */

import type { Alert, SensorData, Stats } from '../types/live'
import { usePendingSensors } from './usePendingSensors'

export type { Alert, SensorData, Stats } from '../types/live'

export function useWebSocket() {
  const wsUrl = 'ws://localhost:8000/ws/live'
  let socket: WebSocket | null = null
  let reconnectTimer: number | null = null

  const connected = ref(false)
  const sensorData = ref<SensorData[]>([])
  const alerts = ref<Alert[]>([])
  const stats = ref<Stats | null>(null)
  const lastUpdate = ref<number>(0)
  const { clearReceivedSensors } = usePendingSensors()

  function connect() {
    if (socket && socket.readyState === WebSocket.OPEN) return

    socket = new WebSocket(wsUrl)

    socket.onopen = () => {
      connected.value = true
      console.log('[WebSocket] Connected')
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'sensor_update') {
          sensorData.value = payload.sensors || []
          alerts.value = payload.alerts || []
          clearReceivedSensors(sensorData.value)
          stats.value = payload.stats || null
          lastUpdate.value = Date.now()
        }
      } catch (e) {
        console.error('[WebSocket] Parse error:', e)
      }
    }

    socket.onclose = () => {
      connected.value = false
      console.log('[WebSocket] Disconnected, reconnecting in 3s...')
      reconnectTimer = window.setTimeout(connect, 3000)
    }

    socket.onerror = (err) => {
      console.error('[WebSocket] Error:', err)
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (socket) {
      socket.close()
      socket = null
    }
    connected.value = false
  }

  onMounted(() => {
    connect()
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected,
    sensorData,
    alerts,
    stats,
    lastUpdate
  }
}
