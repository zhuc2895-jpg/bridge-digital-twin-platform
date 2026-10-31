<template>
  <div class="sensor-marker" :class="statusClass" :style="positionStyle">
    <div class="marker-dot" @click="$emit('select', sensor.sensor_id)">
      <div class="inner-dot"></div>
    </div>
    <div class="marker-tooltip">
      <div class="tooltip-name">{{ sensor.name }}</div>
      <div class="tooltip-value">{{ sensor.value.toFixed(2) }} {{ unit }}</div>
      <div class="tooltip-status">{{ statusLabel }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SensorReading } from '../composables/useWebSocket'

const props = defineProps<{
  sensor: SensorReading
  x: number  // 0~1 相对位置
  y: number  // 0~1 相对位置
}>()

defineEmits<{
  select: [sensorId: string]
}>()

const unit = computed(() => {
  const map: Record<string, string> = {
    strain: 'με', displacement: 'mm',
    acceleration: 'm/s²', temperature: '°C'
  }
  return map[props.sensor.type] || ''
})

const statusLabel = computed(() => {
  if (props.sensor.type === 'strain') {
    if (props.sensor.value > 600) return '⚠ 危险'
    if (props.sensor.value > 450) return '⚠ 警告'
    if (props.sensor.value > 300) return '● 注意'
  }
  if (props.sensor.type === 'displacement') {
    if (props.sensor.value > 80) return '⚠ 危险'
    if (props.sensor.value > 50) return '⚠ 警告'
    if (props.sensor.value > 30) return '● 注意'
  }
  return '✓ 正常'
})

const statusClass = computed(() => {
  if (statusLabel.value.includes('危险')) return 'danger'
  if (statusLabel.value.includes('警告')) return 'warning'
  if (statusLabel.value.includes('注意')) return 'caution'
  return 'normal'
})

const positionStyle = computed(() => ({
  left: `${props.x * 100}%`,
  top: `${props.y * 100}%`
}))
</script>

<style scoped>
.sensor-marker {
  position: absolute;
  transform: translate(-50%, -50%);
  z-index: 5;
  cursor: pointer;
}

.marker-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  border: 2px solid #52c41a;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.marker-dot:hover {
  transform: scale(1.4);
}
.inner-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #52c41a;
}

.caution .marker-dot { border-color: #fadb14; }
.caution .inner-dot { background: #fadb14; }
.warning .marker-dot { border-color: #fa8c16; }
.warning .inner-dot { background: #fa8c16; }
.danger .marker-dot {
  border-color: #ff4d4f;
  animation: danger-pulse 1s infinite;
}
.danger .inner-dot { background: #ff4d4f; }

.marker-tooltip {
  display: none;
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 11px;
  white-space: nowrap;
  z-index: 10;
}
.marker-dot:hover + .marker-tooltip {
  display: block;
}
.tooltip-name { font-weight: 600; margin-bottom: 2px; }
.tooltip-value { color: #58a6ff; }
.tooltip-status { font-size: 10px; margin-top: 2px; }

@keyframes danger-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.6); }
  50% { box-shadow: 0 0 0 8px rgba(255, 77, 79, 0); }
}
</style>
