<template>
  <div class="alert-panel">
    <div class="panel-header">
      <h3>🚨 智能预警</h3>
      <div class="alert-summary">
        <span class="badge red">{{ store.alertCountByLevel.red }} 红色</span>
        <span class="badge orange">{{ store.alertCountByLevel.orange }} 橙色</span>
        <span class="badge yellow">{{ store.alertCountByLevel.yellow }} 黄色</span>
      </div>
    </div>

    <!-- 告警列表 -->
    <div class="alert-list" v-if="store.latestAlerts.length > 0">
      <div
        v-for="alert in store.latestAlerts"
        :key="alert.id"
        class="alert-item"
        :class="alert.level"
      >
        <div class="alert-icon">
          <span v-if="alert.level === 'red'">🔴</span>
          <span v-else-if="alert.level === 'orange'">🟠</span>
          <span v-else-if="alert.level === 'yellow'">🟡</span>
          <span v-else>🟢</span>
        </div>
        <div class="alert-content">
          <div class="alert-header">
            <span class="alert-source">{{ sourceLabel(alert.source) }}</span>
            <span class="alert-time">{{ formatTime(alert.timestamp) }}</span>
          </div>
          <div class="alert-message">{{ alert.message }}</div>
          <div class="alert-detail">
            <span>{{ alert.sensor_name }}</span>
            <span class="alert-value">
              当前值: {{ alert.value === null ? '--' : alert.value.toFixed(2) }}
            </span>
            <span class="alert-threshold">阈值: {{ alert.threshold ?? '--' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 无告警 -->
    <div class="no-alerts" v-else>
      <div class="no-alerts-icon">✅</div>
      <div class="no-alerts-text">系统运行正常，无活跃告警</div>
    </div>

    <!-- 手动异常注入按钮 -->
    <div class="inject-section">
      <button class="inject-btn" @click="injectAnomaly('S01')">
        ⚡ 手动注入异常 (S01)
      </button>
      <button class="inject-btn" @click="injectAnomaly('D01')">
        ⚡ 手动注入异常 (D01)
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useBridgeStore } from '../stores/bridgeStore'
import type { AlertSource } from '../types/live'

const store = useBridgeStore()

function sourceLabel(source: AlertSource): string {
  const map: Record<AlertSource, string> = {
    rule: '物理阈值',
    ai_stalwart: 'STALWART',
    ai_gan_ae: 'GAN+AE',
    ai_isolation_forest: 'Isolation Forest',
    ai_dual_confirm: '双模型确认',
    ai_feature_arbitration: '特征仲裁'
  }
  return map[source] || source
}

function formatTime(ts: number | null): string {
  return ts === null ? "--" : new Date(ts * 1000).toLocaleTimeString()
}

async function injectAnomaly(sensorId: string) {
  try {
    await fetch(`http://localhost:8000/api/analysis/inject-anomaly?sensor_id=${sensorId}`, {
      method: 'POST'
    })
    console.log(`[AlertPanel] Anomaly injected to ${sensorId}`)
  } catch (e) {
    console.error('Inject anomaly error:', e)
  }
}
</script>

<style scoped>
.alert-panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-header h3 {
  margin: 0;
  font-size: 15px;
  color: #f0f6fc;
}

.alert-summary {
  display: flex;
  gap: 8px;
}
.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.badge.red { background: rgba(255, 77, 79, 0.2); color: #ff4d4f; }
.badge.orange { background: rgba(250, 140, 22, 0.2); color: #fa8c16; }
.badge.yellow { background: rgba(250, 219, 20, 0.2); color: #fadb14; }

.alert-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.alert-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  background: #0d1117;
  border-left: 3px solid #30363d;
}
.alert-item.red { border-left-color: #ff4d4f; background: rgba(255, 77, 79, 0.05); }
.alert-item.orange { border-left-color: #fa8c16; background: rgba(250, 140, 22, 0.05); }
.alert-item.yellow { border-left-color: #fadb14; background: rgba(250, 219, 20, 0.05); }

.alert-icon { font-size: 18px; flex-shrink: 0; margin-top: 2px; }

.alert-content { flex: 1; min-width: 0; }
.alert-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
.alert-source { font-size: 11px; color: #58a6ff; font-weight: 600; }
.alert-time { font-size: 10px; color: #8b949e; }
.alert-message { font-size: 13px; color: #f0f6fc; margin-bottom: 4px; }
.alert-detail { display: flex; gap: 12px; font-size: 11px; color: #8b949e; }
.alert-value { color: #ffa198; }
.alert-threshold { color: #8b949e; }

.no-alerts {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8b949e;
}
.no-alerts-icon { font-size: 40px; margin-bottom: 12px; }
.no-alerts-text { font-size: 14px; }

.inject-section {
  padding: 12px 16px;
  border-top: 1px solid #30363d;
  display: flex;
  gap: 8px;
}
.inject-btn {
  flex: 1;
  padding: 8px 12px;
  background: #21262d;
  color: #f0f6fc;
  border: 1px solid #30363d;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.inject-btn:hover {
  background: #30363d;
  border-color: #ff4d4f;
  color: #ff4d4f;
}
</style>
