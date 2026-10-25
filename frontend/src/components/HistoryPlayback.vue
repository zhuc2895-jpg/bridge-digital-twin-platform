<template>
  <div class="history-playback">
    <div class="panel-header">
      <h3>⏮️ 历史回放</h3>
      <div class="playback-controls">
        <select v-model="selectedSensor" class="sensor-select">
          <option value="">选择传感器</option>
          <option v-for="s in store.sensorData" :key="s.sensor_id" :value="s.sensor_id">
            {{ s.sensor_id }} - {{ s.name }}
          </option>
        </select>
        <select v-model="timeRange" class="time-select">
          <option :value="10">最近10分钟</option>
          <option :value="30">最近30分钟</option>
          <option :value="60">最近60分钟</option>
          <option :value="120">最近2小时</option>
        </select>
        <button class="btn" @click="loadHistory" :disabled="!selectedSensor">
          🔍 加载
        </button>
      </div>
    </div>

    <!-- 历史数据图表 -->
    <div class="chart-area" ref="historyChartRef">
      <div v-if="!historyData.length" class="empty-state">
        <div class="empty-icon">📊</div>
        <div>选择传感器并点击"加载"查看历史数据</div>
      </div>
      <div v-else class="history-table-wrapper">
        <table class="history-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>传感器</th>
              <th>类型</th>
              <th>数值</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in displayedHistory" :key="i" :class="getRowClass(row)">
              <td>{{ formatTime(row.timestamp) }}</td>
              <td>{{ row.name }}</td>
              <td>{{ row.type }}</td>
              <td class="value-cell">{{ row.value.toFixed(4) }}</td>
              <td>
                <span class="status-tag" :class="getStatusClass(row)">
                  {{ getStatusLabel(row) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 统计摘要 -->
    <div class="stats-bar" v-if="historyStats">
      <div class="stat-item">
        <span class="stat-label">数据点</span>
        <span class="stat-num">{{ historyStats.count }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">均值</span>
        <span class="stat-num">{{ historyStats.mean }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">最大值</span>
        <span class="stat-num max">{{ historyStats.max }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">最小值</span>
        <span class="stat-num min">{{ historyStats.min }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBridgeStore } from '../stores/bridgeStore'

const store = useBridgeStore()
const historyChartRef = ref<HTMLDivElement>()

const selectedSensor = ref('')
const timeRange = ref(60)
const historyData = ref<any[]>([])
const historyStats = ref<any>(null)

async function loadHistory() {
  if (!selectedSensor.value) return
  try {
    const res = await fetch(
      `http://localhost:8000/api/sensors/${selectedSensor.value}/history?minutes=${timeRange.value}`
    )
    const json = await res.json()
    historyData.value = json.data || []

    // 计算统计
    if (historyData.value.length > 0) {
      const values = historyData.value.map((d: any) => d.value)
      historyStats.value = {
        count: values.length,
        mean: (values.reduce((a: number, b: number) => a + b, 0) / values.length).toFixed(4),
        max: Math.max(...values).toFixed(4),
        min: Math.min(...values).toFixed(4)
      }
    }
  } catch (e) {
    console.error('Load history error:', e)
  }
}

const displayedHistory = computed(() => {
  // 显示最近100条
  return historyData.value.slice(-100).reverse()
})

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

function getRowClass(row: any): string {
  if (row.type === 'strain' && row.value > 450) return 'row-danger'
  if (row.type === 'strain' && row.value > 300) return 'row-warning'
  if (row.type === 'displacement' && row.value > 50) return 'row-danger'
  if (row.type === 'displacement' && row.value > 30) return 'row-warning'
  return ''
}

function getStatusLabel(row: any): string {
  if (row.type === 'strain') {
    if (row.value > 600) return '危险'
    if (row.value > 450) return '警告'
    if (row.value > 300) return '注意'
  }
  if (row.type === 'displacement') {
    if (row.value > 80) return '危险'
    if (row.value > 50) return '警告'
    if (row.value > 30) return '注意'
  }
  return '正常'
}

function getStatusClass(row: any): string {
  const label = getStatusLabel(row)
  if (label === '危险') return 'danger'
  if (label === '警告') return 'warning'
  if (label === '注意') return 'caution'
  return 'normal'
}
</script>

<style scoped>
.history-playback {
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
  flex-wrap: wrap;
  gap: 8px;
}
.panel-header h3 {
  margin: 0;
  font-size: 15px;
  color: #f0f6fc;
}

.playback-controls {
  display: flex;
  gap: 8px;
}
.sensor-select, .time-select {
  background: #21262d;
  color: #c9d1d9;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
}
.btn {
  background: #238636;
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}
.btn:disabled {
  background: #21262d;
  color: #484f58;
  cursor: not-allowed;
}

.chart-area {
  flex: 1;
  overflow: auto;
  padding: 12px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #8b949e;
  font-size: 14px;
}
.empty-icon { font-size: 36px; margin-bottom: 12px; }

.history-table-wrapper {
  max-height: 100%;
  overflow: auto;
}
.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.history-table th {
  text-align: left;
  padding: 8px 10px;
  color: #8b949e;
  border-bottom: 1px solid #30363d;
  position: sticky;
  top: 0;
  background: #161b22;
}
.history-table td {
  padding: 6px 10px;
  color: #c9d1d9;
  border-bottom: 1px solid #21262d;
}
.value-cell { font-family: 'Consolas', monospace; color: #58a6ff; }
.row-danger { background: rgba(255, 77, 79, 0.08); }
.row-warning { background: rgba(250, 140, 22, 0.06); }

.status-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}
.status-tag.normal { background: rgba(82, 196, 26, 0.15); color: #52c41a; }
.status-tag.caution { background: rgba(250, 219, 20, 0.15); color: #fadb14; }
.status-tag.warning { background: rgba(250, 140, 22, 0.15); color: #fa8c16; }
.status-tag.danger { background: rgba(255, 77, 79, 0.15); color: #ff4d4f; }

.stats-bar {
  display: flex;
  gap: 0;
  border-top: 1px solid #30363d;
}
.stat-item {
  flex: 1;
  padding: 10px;
  text-align: center;
  border-right: 1px solid #30363d;
}
.stat-item:last-child { border-right: none; }
.stat-label { display: block; font-size: 11px; color: #8b949e; margin-bottom: 4px; }
.stat-num { font-size: 16px; font-weight: 700; color: #58a6ff; }
.stat-num.max { color: #ffa198; }
.stat-num.min { color: #7ee787; }
</style>
