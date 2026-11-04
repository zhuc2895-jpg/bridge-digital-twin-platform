import { computed, onMounted, onUnmounted, ref } from 'vue'
import { apiFetch, websocketUrl } from '../api'
import type { Alert, PressureField, SensorReading, Stats } from '../types/live'

export type MonitoringMode = 'live' | 'replay'

export interface MonitoringSessionAdapters {
  createSocket?: (url: string) => WebSocket
  request?: (path: string, init?: RequestInit) => Promise<Response>
  reconnectMs?: number
  replayTickMs?: number
  replayStepSeconds?: number
}

export function useMonitoringSession(options: MonitoringSessionAdapters = {}) {
  const createSocket = options.createSocket ?? ((url: string) => new WebSocket(url))
  const request = options.request ?? apiFetch
  const reconnectMs = options.reconnectMs ?? 3000
  const replayTickMs = options.replayTickMs ?? 500
  const replayStepSeconds = options.replayStepSeconds ?? 10

  const connected = ref(false)
  const sensors = ref<SensorReading[]>([])
  const alerts = ref<Alert[]>([])
  const stats = ref<Stats | null>(null)
  const pressureField = ref<PressureField | null>(null)
  const lastUpdate = ref(0)
  const frameVersion = ref(0)
  const connectionError = ref('')
  const replayError = ref('')

  const mode = ref<MonitoringMode>('live')
  const historyRange = ref({ start: 0, end: 0, hasData: false })
  const replayPlaying = ref(false)
  const replaySpeed = ref(4)
  const replayCurrentTs = ref(0)
  const replaySnapshot = ref<Record<string, SensorReading>>({})
  const replayAlerts = ref<Alert[]>([])

  let socket: WebSocket | null = null
  let reconnectTimer: number | null = null
  let replayTimer: number | null = null
  let intentionalClose = false

  const replayTimeText = computed(() => {
    if (!replayCurrentTs.value) return '--:--:--'
    return new Date(replayCurrentTs.value * 1000).toLocaleString('zh-CN', {
      hour12: false
    })
  })

  const replayProgress = computed(() => {
    const { start, end, hasData } = historyRange.value
    if (!hasData || end <= start) return 0
    return Math.min(
      100,
      Math.max(0, ((replayCurrentTs.value - start) / (end - start)) * 100)
    )
  })

  function clearReconnect() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function closeSocket() {
    intentionalClose = true
    clearReconnect()
    if (socket) {
      socket.close()
      socket = null
    }
    connected.value = false
  }

  function connect() {
    if (mode.value !== 'live') return
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return
    }
    clearReconnect()
    intentionalClose = false
    socket = createSocket(websocketUrl('/ws/live'))

    socket.onopen = () => {
      connected.value = true
      connectionError.value = ''
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type !== 'sensor_update' || mode.value !== 'live') return
        sensors.value = payload.sensors || []
        alerts.value = payload.alerts || []
        stats.value = payload.stats || null
        pressureField.value = payload.pressure || null
        lastUpdate.value = Date.now()
        frameVersion.value += 1
      } catch (error) {
        connectionError.value = error instanceof Error ? error.message : 'Invalid live frame'
      }
    }

    socket.onclose = () => {
      connected.value = false
      if (intentionalClose || mode.value !== 'live') return
      connectionError.value = '实时连接断开'
      reconnectTimer = window.setTimeout(connect, reconnectMs)
    }

    socket.onerror = () => {
      connected.value = false
      connectionError.value = '实时连接错误'
    }
  }

  async function loadHistoryRange() {
    replayError.value = ''
    try {
      const response = await request('/api/sensors/history/timerange')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      if (data.has_data) {
        historyRange.value = {
          start: data.start,
          end: data.end,
          hasData: true
        }
        replayCurrentTs.value = data.start
      }
    } catch (error) {
      replayError.value = error instanceof Error ? error.message : '无法读取历史区间'
    }
  }

  function stopReplayTimer() {
    if (replayTimer !== null) {
      window.clearInterval(replayTimer)
      replayTimer = null
    }
  }

  function startReplayTimer() {
    stopReplayTimer()
    replayTimer = window.setInterval(async () => {
      if (!replayPlaying.value || mode.value !== 'replay') return
      replayCurrentTs.value += replayStepSeconds * replaySpeed.value
      if (replayCurrentTs.value >= historyRange.value.end) {
        replayCurrentTs.value = historyRange.value.end
        replayPlaying.value = false
        stopReplayTimer()
      }
      await loadReplaySnapshot()
    }, replayTickMs)
  }

  function enterReplay() {
    if (!historyRange.value.hasData) return
    mode.value = 'replay'
    replayPlaying.value = true
    pressureField.value = null
    closeSocket()
    startReplayTimer()
  }

  function toggleReplay() {
    if (!historyRange.value.hasData) return
    if (mode.value === 'live') {
      enterReplay()
      return
    }
    replayPlaying.value = !replayPlaying.value
    if (replayPlaying.value) startReplayTimer()
    else stopReplayTimer()
  }

  async function loadReplaySnapshot() {
    replayError.value = ''
    try {
      const snapshotResponse = await request(
        `/api/sensors/history/snapshot?ts=${replayCurrentTs.value}`
      )
      if (!snapshotResponse.ok) {
        throw new Error(`Snapshot HTTP ${snapshotResponse.status}`)
      }
      replaySnapshot.value = await snapshotResponse.json()
      const snapshotSensors = Object.values(replaySnapshot.value) as SensorReading[]
      if (snapshotSensors.length) {
        sensors.value = snapshotSensors
        frameVersion.value += 1
      }

      const alertsResponse = await request(
        `/api/sensors/history/alerts?start=${replayCurrentTs.value - 3600}&end=${replayCurrentTs.value}`
      )
      if (!alertsResponse.ok) {
        throw new Error(`Alerts HTTP ${alertsResponse.status}`)
      }
      const alertPayload = await alertsResponse.json()
      replayAlerts.value = alertPayload.alerts || []
      alerts.value = replayAlerts.value
    } catch (error) {
      replayError.value = error instanceof Error ? error.message : '回放加载失败'
    }
  }

  async function seekReplay() {
    if (replayPlaying.value) return
    mode.value = 'replay'
    pressureField.value = null
    closeSocket()
    await loadReplaySnapshot()
  }

  async function resetReplay() {
    replayCurrentTs.value = historyRange.value.start
    mode.value = 'replay'
    pressureField.value = null
    closeSocket()
    await loadReplaySnapshot()
  }

  function exitReplay() {
    mode.value = 'live'
    replayPlaying.value = false
    stopReplayTimer()
    replaySnapshot.value = {}
    replayAlerts.value = []
    connectionError.value = ''
    connect()
  }

  onMounted(() => {
    connect()
    void loadHistoryRange()
  })

  onUnmounted(() => {
    stopReplayTimer()
    closeSocket()
  })

  return {
    connected,
    sensors,
    alerts,
    stats,
    pressureField,
    lastUpdate,
    frameVersion,
    connectionError,
    replayError,
    mode,
    historyRange,
    replayPlaying,
    replaySpeed,
    replayCurrentTs,
    replaySnapshot,
    replayTimeText,
    replayProgress,
    toggleReplay,
    seekReplay,
    resetReplay,
    exitReplay
  }
}
