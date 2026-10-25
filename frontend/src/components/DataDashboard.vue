<template>
  <div class="data-dashboard">
    <!-- 顶部统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ store.stats?.sensor_count || 0 }}</div>
        <div class="stat-label">传感器在线</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ store.stats?.total_readings?.toLocaleString() || 0 }}</div>
        <div class="stat-label">累计读数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ store.stats?.throughput || 0 }}</div>
        <div class="stat-label">吞吐量 (条/秒)</div>
      </div>
      <div class="stat-card alert">
        <div class="stat-value">{{ store.alertCountByLevel.red + store.alertCountByLevel.orange }}</div>
        <div class="stat-label">活跃告警</div>
      </div>
    </div>

    <!-- 实时数据表格 -->
    <div class="panel">
      <div class="panel-header">
        <h3>📡 实时传感器数据</h3>
        <span class="update-time" v-if="store.lastUpdate">
          更新于 {{ new Date(store.lastUpdate).toLocaleTimeString() }}
        </span>
      </div>
      <div class="sensor-grid">
        <div
          v-for="sensor in store.sensorData"
          :key="sensor.sensor_id"
          class="sensor-card"
          :class="getCardClass(sensor)"
          @click="store.selectSensor(sensor.sensor_id)"
        >
          <div class="sensor-header">
            <span class="sensor-id">{{ sensor.sensor_id }}</span>
            <span class="sensor-type">{{ typeLabel(sensor.type) }}</span>
          </div>
          <div class="sensor-name">{{ sensor.name }}</div>
          <div class="sensor-value">{{ sensor.value.toFixed(2) }}</div>
          <div class="sensor-unit">{{ unitLabel(sensor.type) }}</div>
        </div>
      </div>
    </div>

    <!-- 实时趋势图（ECharts 占位） -->
    <div class="panel">
      <div class="panel-header">
        <h3>📈 实时趋势</h3>
        <select v-model="store.selectedChartSensor" class="chart-select">
          <option v-for="s in store.sensorData" :key="s.sensor_id" :value="s.sensor_id">
            {{ s.sensor_id }} - {{ s.name }}
          </option>
        </select>
      </div>
      <div class="chart-container" ref="chartRef">
        <!-- ECharts 渲染区域 -->
        <div class="chart-placeholder">
          📊 ECharts 实时趋势图（需引入 echarts 库）
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useBridgeStore } from '../stores/bridgeStore'

const store = useBridgeStore()
const chartRef = ref<HTMLDivElement>()

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    strain: '应变',
    displacement: '位移',
    acceleration: '加速度',
    temperature: '温度'
  }
  return map[type] || type
}

function unitLabel(type: string): string {
  const map: Record<string, string> = {
    strain: 'με',
    displacement: 'mm',
    acceleration: 'm/s²',
    temperature: '°C'
  }
  return map[type] || ''
}

function getCardClass(sensor: any): string {
  if (sensor.type === 'strain') {
    if (sensor.value > 600) return 'danger'
    if (sensor.value > 450) return 'warning'
    if (sensor.value > 300) return 'caution'
  }
  if (sensor.type === 'displacement') {
    if (sensor.value > 80) return 'danger'
    if (sensor.value > 50) return 'warning'
    if (sensor.value > 30) return 'caution'
  }
  return 'normal'
}
</script>

<style scoped>
.data-dashboard {
  padding: 16px;
  height: 100%;
  overflow-y: auto;
  background: #0d1117;
  color: #c9d1d9;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 14px;
  text-align: center;
}
.stat-card.alert {
  border-color: #ff4d4f;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #58a6ff;
}
.stat-card.alert .stat-value {
  color: #ff4d4f;
}
.stat-label {
  font-size: 12px;
  color: #8b949e;
  margin-top: 4px;
}

.panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
}
.panel-header h3 {
  margin: 0;
  font-size: 15px;
  color: #f0f6fc;
}
.update-time {
  font-size: 12px;
  color: #8b949e;
}

.sensor-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 12px;
}

.sensor-card {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.sensor-card:hover {
  border-color: #58a6ff;
  transform: translateY(-2px);
}
.sensor-card.caution { border-color: #fadb14; }
.sensor-card.warning { border-color: #fa8c16; }
.sensor-card.danger { border-color: #ff4d4f; animation: pulse 1.5s infinite; }

.sensor-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.sensor-id { font-size: 11px; color: #58a6ff; font-weight: 600; }
.sensor-type { font-size: 10px; color: #8b949e; background: #21262d; padding: 2px 6px; border-radius: 4px; }
.sensor-name { font-size: 12px; color: #c9d1d9; margin-bottom: 8px; }
.sensor-value { font-size: 22px; font-weight: 700; color: #f0f6fc; }
.sensor-unit { font-size: 11px; color: #8b949e; }

.chart-select {
  background: #21262d;
  color: #c9d1d9;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 13px;
}
.chart-container {
  height: 280px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chart-placeholder {
  color: #8b949e;
  font-size: 14px;
}

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(255, 77, 79, 0); }
}
</style>
