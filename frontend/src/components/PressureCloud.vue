<template>
  <section class="pressure-panel">
    <div class="pressure-header">
      <div>
        <div class="pressure-title">实时响应压力云图</div>
        <div class="pressure-subtitle">
          归一化结构响应指数 · abs(value) / red_threshold
        </div>
      </div>
      <div class="pressure-actions">
        <span class="pressure-state" :class="statusClass">{{ statusText }}</span>
        <button class="overlay-button" type="button" @click="$emit('toggle-overlay')">
          {{ overlayEnabled ? '隐藏 3D 叠加' : '3D 叠加' }}
        </button>
      </div>
    </div>

    <div class="pressure-content">
      <div class="canvas-wrap">
        <canvas ref="canvasRef" aria-label="桥梁响应压力云图"></canvas>
        <div v-if="!field || field.coverage === 0" class="empty-cloud">
          <span>等待实时压力场数据</span>
          <small>传感器接入后将自动渲染</small>
        </div>
      </div>

      <div class="pressure-metrics">
        <div class="metric">
          <span class="metric-label">峰值指数</span>
          <strong class="metric-value" :class="statusClass">{{ field?.max.toFixed(3) ?? '--' }}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">峰值测点</span>
          <strong class="metric-value">{{ field?.max_sensor_id ?? '--' }}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">覆盖测点</span>
          <strong class="metric-value">{{ field?.coverage ?? 0 }}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">更新时间</span>
          <strong class="metric-value small">{{ updatedAt }}</strong>
        </div>
      </div>
    </div>

    <div class="pressure-legend">
      <span>0.0</span>
      <div class="gradient-bar"></div>
      <span>1.0+</span>
      <div class="legend-levels">
        <i class="g"></i>正常
        <i class="y"></i>注意
        <i class="o"></i>警告
        <i class="r"></i>危险
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { PressureField } from '../types/live'

const props = defineProps<{
  field: PressureField | null
  overlayEnabled: boolean
}>()

defineEmits<{
  'toggle-overlay': []
}>()

const canvasRef = ref<HTMLCanvasElement>()
let resizeObserver: ResizeObserver | null = null

const statusText = computed(() => {
  if (!props.field || props.field.coverage === 0) return '无数据'
  const labels: Record<string, string> = {
    normal: '正常',
    yellow: '注意',
    orange: '警告',
    red: '危险',
    unknown: '未知'
  }
  return labels[props.field.max_level] || props.field.max_level
})

const statusClass = computed(() => props.field?.max_level || 'normal')

const updatedAt = computed(() => {
  if (!props.field?.generated_at) return '--:--:--'
  return new Date(props.field.generated_at * 1000).toLocaleTimeString('zh-CN', {
    hour12: false
  })
})

const colorStops = [
  [0.0, [12, 74, 110]],
  [0.25, [2, 132, 199]],
  [0.5, [34, 197, 94]],
  [0.75, [250, 204, 21]],
  [0.9, [249, 115, 22]],
  [1.25, [239, 68, 68]]
] as const

function colorFor(value: number): [number, number, number] {
  const ratio = Math.max(0, Math.min(1.25, value))
  for (let index = 1; index < colorStops.length; index += 1) {
    const previous = colorStops[index - 1]
    const current = colorStops[index]
    if (ratio <= current[0]) {
      const span = current[0] - previous[0] || 1
      const t = (ratio - previous[0]) / span
      return [
        Math.round(previous[1][0] + (current[1][0] - previous[1][0]) * t),
        Math.round(previous[1][1] + (current[1][1] - previous[1][1]) * t),
        Math.round(previous[1][2] + (current[1][2] - previous[1][2]) * t)
      ]
    }
  }
  return [239, 68, 68]
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const width = canvas.clientWidth || 500
  const height = canvas.clientHeight || 220
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  const context = canvas.getContext('2d')
  if (!context) return
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, width, height)
  context.fillStyle = '#111214'
  context.fillRect(0, 0, width, height)

  const plot = { left: 28, top: 12, width: width - 52, height: height - 44 }
  const field = props.field
  if (!field || field.coverage === 0 || field.values.length === 0) {
    drawAxes(context, plot, field)
    return
  }

  const { nx, nz } = field.grid
  const offscreen = document.createElement('canvas')
  offscreen.width = nx
  offscreen.height = nz
  const offscreenContext = offscreen.getContext('2d')
  if (offscreenContext) {
    const image = offscreenContext.createImageData(nx, nz)
    for (let zIndex = 0; zIndex < nz; zIndex += 1) {
      for (let xIndex = 0; xIndex < nx; xIndex += 1) {
        const value = field.values[zIndex * nx + xIndex] ?? 0
        const [red, green, blue] = colorFor(value)
        const targetRow = nz - 1 - zIndex
        const offset = (targetRow * nx + xIndex) * 4
        image.data[offset] = red
        image.data[offset + 1] = green
        image.data[offset + 2] = blue
        image.data[offset + 3] = 255
      }
    }
    offscreenContext.putImageData(image, 0, 0)
    context.save()
    context.imageSmoothingEnabled = true
    context.imageSmoothingQuality = 'high'
    context.drawImage(offscreen, plot.left, plot.top, plot.width, plot.height)
    context.restore()
  }

  context.strokeStyle = 'rgba(148, 163, 184, 0.25)'
  context.lineWidth = 1
  for (let xIndex = 0; xIndex < nx; xIndex += 4) {
    const x = plot.left + (plot.width * xIndex) / (nx - 1)
    context.beginPath()
    context.moveTo(x, plot.top)
    context.lineTo(x, plot.top + plot.height)
    context.stroke()
  }
  for (let zIndex = 0; zIndex < nz; zIndex += 2) {
    const y = plot.top + (plot.height * zIndex) / (nz - 1)
    context.beginPath()
    context.moveTo(plot.left, y)
    context.lineTo(plot.left + plot.width, y)
    context.stroke()
  }

  for (const point of field.points) {
    const xRatio = (point.x - field.grid.x_min) / (field.grid.x_max - field.grid.x_min)
    const zRatio = (point.z - field.grid.z_min) / (field.grid.z_max - field.grid.z_min)
    const x = plot.left + xRatio * plot.width
    const y = plot.top + (1 - zRatio) * plot.height
    context.beginPath()
    context.arc(x, y, 4.5, 0, Math.PI * 2)
    context.fillStyle = '#f8fafc'
    context.fill()
    context.lineWidth = 2
    context.strokeStyle = colorFor(point.ratio).reduce(
      (value, channel) => value + channel.toString(16).padStart(2, '0'),
      '#'
    )
    context.stroke()
    context.fillStyle = '#e2e8f0'
    context.font = '10px Consolas, monospace'
    context.textAlign = 'center'
    context.fillText(point.sensor_id, x, Math.max(plot.top + 10, y - 8))
  }

  drawAxes(context, plot, field)
}

function drawAxes(
  context: CanvasRenderingContext2D,
  plot: { left: number; top: number; width: number; height: number },
  field: PressureField | null
) {
  context.strokeStyle = '#334155'
  context.lineWidth = 1
  context.strokeRect(plot.left, plot.top, plot.width, plot.height)
  context.fillStyle = '#8b949e'
  context.font = '10px Consolas, monospace'
  context.textAlign = 'center'
  context.fillText(field ? `${field.grid.x_min.toFixed(0)} m` : '-60 m', plot.left, plot.top + plot.height + 16)
  context.fillText('0', plot.left + plot.width / 2, plot.top + plot.height + 16)
  context.fillText(field ? `${field.grid.x_max.toFixed(0)} m` : '60 m', plot.left + plot.width, plot.top + plot.height + 16)
  context.save()
  context.translate(10, plot.top + plot.height / 2)
  context.rotate(-Math.PI / 2)
  context.fillText('桥面横向', 0, 0)
  context.restore()
}

watch(() => props.field, draw, { flush: 'post' })

onMounted(() => {
  resizeObserver = new ResizeObserver(() => draw())
  if (canvasRef.value) resizeObserver.observe(canvasRef.value)
  draw()
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.pressure-panel {
  overflow: hidden;
  border: 1px solid var(--ink, #111214);
  background: rgba(244, 243, 239, 0.94);
  box-shadow: 8px 8px 0 rgba(17, 18, 20, 0.12);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
}
.pressure-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px 7px;
  border-bottom: 1px solid var(--line, rgba(17, 18, 20, 0.18));
}
.pressure-title { color: var(--ink, #111214); font-family: var(--cjk, sans-serif); font-size: 10px; font-weight: 600; letter-spacing: 0.06em; }
.pressure-subtitle { margin-top: 2px; color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 6.2px; letter-spacing: 0.2px; line-height: 1.4; }
.pressure-actions { display: flex; align-items: center; gap: 5px; flex: none; }
.pressure-state { padding: 2px 5px; background: var(--ink, #111214); color: var(--paper, #f4f3ef); font-family: var(--mono, monospace); font-size: 6px; letter-spacing: 0.35px; }
.pressure-state.yellow { background: var(--amber, #d9a300); color: var(--ink, #111214); }
.pressure-state.orange { background: var(--orange, #ff6a00); color: var(--ink, #111214); }
.pressure-state.red { background: var(--red, #e23b12); color: var(--paper, #f4f3ef); }
.pressure-state.unknown { background: var(--faint, #b7b3ab); color: var(--ink, #111214); }
.overlay-button { padding: 3px 5px; border: 1px solid rgba(17, 18, 20, 0.4); background: transparent; color: var(--ink, #111214); font-family: var(--mono, monospace); font-size: 6px; letter-spacing: 0.35px; cursor: pointer; }
.overlay-button:hover { border-color: var(--ink, #111214); background: var(--ink, #111214); color: var(--paper, #f4f3ef); }
.pressure-content { display: grid; grid-template-columns: minmax(0, 1fr) 92px; border-bottom: 1px solid var(--line, rgba(17, 18, 20, 0.18)); }
.canvas-wrap { position: relative; min-width: 0; }
canvas { display: block; width: 100%; height: 132px; background: var(--ink, #111214); }
.empty-cloud { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; background: rgba(17, 18, 20, 0.82); color: #b9b6af; font-family: var(--cjk, sans-serif); font-size: 9px; }
.empty-cloud small { color: #77736b; font-size: 7px; }
.pressure-metrics { display: grid; grid-template-rows: repeat(4, 1fr); border-left: 1px solid var(--line, rgba(17, 18, 20, 0.18)); }
.metric { display: flex; flex-direction: column; justify-content: center; padding: 4px 7px; border-bottom: 1px solid var(--line-soft, rgba(17, 18, 20, 0.1)); }
.metric:last-child { border-bottom: 0; }
.metric-label { color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 5.8px; letter-spacing: 0.35px; }
.metric-value { color: var(--ink, #111214); font-family: var(--mono, monospace); font-size: 10.5px; font-weight: 500; line-height: 1.2; }
.metric-value.small { font-size: 7px; }
.metric-value.normal { color: var(--ink, #111214); }
.metric-value.yellow { color: #8a6500; }
.metric-value.orange { color: #c24a00; }
.metric-value.red { color: var(--red, #e23b12); }
.pressure-legend { display: flex; align-items: center; gap: 6px; padding: 5px 10px 7px; color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 5.8px; letter-spacing: 0.2px; }
.gradient-bar { width: 72px; height: 4px; background: linear-gradient(90deg, #0c4a6e, #0284c7, #22c55e, #facc15, #f97316, #ef4444); }
.legend-levels { display: flex; align-items: center; gap: 3px; margin-left: auto; white-space: nowrap; }
.legend-levels i { display: inline-block; width: 4px; height: 4px; margin-left: 4px; background: #22c55e; }
.legend-levels .y { background: #facc15; }
.legend-levels .o { background: #f97316; }
.legend-levels .r { background: #ef4444; }
@media (max-width: 900px) {
  .pressure-content { grid-template-columns: 1fr; }
  .pressure-metrics { grid-template-columns: repeat(4, 1fr); grid-template-rows: none; border-top: 1px solid var(--line, rgba(17, 18, 20, 0.18)); border-left: 0; }
  .metric { border-right: 1px solid var(--line-soft, rgba(17, 18, 20, 0.1)); border-bottom: 0; }
}
</style>
