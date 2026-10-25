<template>
  <div class="main-platform">
    <!-- 顶部标题栏 -->
    <header class="top-bar">
      <div class="logo">
        <span class="logo-icon">🌉</span>
        <span class="logo-text">桥梁数字孪生健康监测平台</span>
        <span class="logo-subtitle">Bridge Digital Twin SHM Platform</span>
      </div>
      <div class="top-actions">
        <div class="connection-status" :class="{ connected: store.connected }">
          <span class="status-dot"></span>
          {{ store.connected ? '实时连接' : '连接断开' }}
        </div>
        <div class="system-time">
          {{ currentTime }}
        </div>
      </div>
    </header>

    <!-- 主体布局 -->
    <div class="main-layout">
      <!-- 左侧：3D 桥梁查看器 -->
      <div class="panel panel-3d">
        <BridgeViewer />
      </div>

      <!-- 右侧：数据面板 -->
      <div class="panel panel-right">
        <!-- 上半：数据仪表盘 -->
        <div class="panel-top">
          <DataDashboard />
        </div>
        <!-- 下半：告警 + 历史 -->
        <div class="panel-bottom">
          <div class="panel-half">
            <AlertPanel />
          </div>
          <div class="panel-half">
            <HistoryPlayback />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useBridgeStore } from '../stores/bridgeStore'
import { useWebSocket } from '../composables/useWebSocket'
import BridgeViewer from '../components/BridgeViewer.vue'
import DataDashboard from '../components/DataDashboard.vue'
import AlertPanel from '../components/AlertPanel.vue'
import HistoryPlayback from '../components/HistoryPlayback.vue'

const store = useBridgeStore()
const { connected, sensorData, alerts, stats, lastUpdate } = useWebSocket()

const currentTime = ref('')
let timeTimer: number

onMounted(() => {
  timeTimer = window.setInterval(() => {
    currentTime.value = new Date().toLocaleString('zh-CN')
  }, 1000)
})

onUnmounted(() => {
  clearInterval(timeTimer)
})

// 同步 WebSocket 数据到 Pinia Store
watch(connected, (val) => store.setConnected(val))
watch(sensorData, (val) => store.updateSensorData(val), { deep: true })
watch(alerts, (val) => store.updateAlerts(val), { deep: true })
watch(stats, (val) => { if (val) store.updateStats(val) })
</script>

<style scoped>
.main-platform {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0d1117;
  color: #c9d1d9;
  overflow: hidden;
}

/* 顶部标题栏 */
.top-bar {
  height: 48px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  flex-shrink: 0;
}
.logo {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.logo-icon { font-size: 22px; }
.logo-text { font-size: 16px; font-weight: 700; color: #f0f6fc; }
.logo-subtitle { font-size: 11px; color: #8b949e; }
.top-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.connection-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8b949e;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #484f58;
}
.connection-status.connected .status-dot {
  background: #52c41a;
  box-shadow: 0 0 6px #52c41a;
}
.system-time {
  font-size: 12px;
  color: #8b949e;
  font-family: 'Consolas', monospace;
}

/* 主体布局 */
.main-layout {
  flex: 1;
  display: flex;
  gap: 0;
  overflow: hidden;
}

.panel {
  overflow: hidden;
}

/* 左侧 3D 视图 - 占 55% */
.panel-3d {
  flex: 55;
  border-right: 1px solid #30363d;
}

/* 右侧面板 - 占 45% */
.panel-right {
  flex: 45;
  display: flex;
  flex-direction: column;
}

.panel-top {
  flex: 45;
  overflow: hidden;
  border-bottom: 1px solid #30363d;
}

.panel-bottom {
  flex: 55;
  display: flex;
  overflow: hidden;
}

.panel-half {
  flex: 1;
  overflow: hidden;
}
.panel-half:first-child {
  border-right: 1px solid #30363d;
}
</style>
