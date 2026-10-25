<template>
  <div class="bridge-viewer" ref="containerRef">
    <!-- Three.js 渲染容器 -->
    <canvas ref="canvasRef"></canvas>

    <!-- 顶部信息栏 -->
    <div class="viewer-overlay top-left">
      <div class="info-badge" v-if="store.connected">
        <span class="dot green"></span> 实时连接
      </div>
      <div class="info-badge" v-else>
        <span class="dot red"></span> 连接断开
      </div>
    </div>

    <!-- 图例 -->
    <div class="viewer-overlay bottom-right legend">
      <div class="legend-item"><span class="swatch green"></span> 正常</div>
      <div class="legend-item"><span class="swatch yellow"></span> 注意</div>
      <div class="legend-item"><span class="swatch orange"></span> 警告</div>
      <div class="legend-item"><span class="swatch red"></span> 危险</div>
    </div>

    <!-- 传感器标注（悬浮标签） -->
    <div
      v-for="sensor in store.sensorData"
      :key="sensor.sensor_id"
      class="sensor-label"
      :class="getSensorClass(sensor)"
      :style="getSensorPosition(sensor)"
      @click="store.selectSensor(sensor.sensor_id)"
    >
      <div class="label-dot"></div>
      <span class="label-text">{{ sensor.name }}</span>
      <span class="label-value">{{ sensor.value.toFixed(1) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useBridgeStore } from '../stores/bridgeStore'

const store = useBridgeStore()
const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()

// Three.js 相关变量（简化版，实际需引入 Three.js）
let scene: any = null
let camera: any = null
let renderer: any = null
let bridgeModel: any = null
let animationId: number = 0

onMounted(() => {
  initThreeJS()
  animate()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', onResize)
  if (renderer) renderer.dispose()
})

function initThreeJS() {
  // TODO: 引入 Three.js 后实现完整 3D 场景
  // import * as THREE from 'three'
  // import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'
  // import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
  //
  // scene = new THREE.Scene()
  // camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 1000)
  // renderer = new THREE.WebGLRenderer({ canvas: canvasRef.value, antialias: true })
  //
  // const loader = new GLTFLoader()
  // loader.load('/models/bridge.glb', (gltf) => {
  //   bridgeModel = gltf.scene
  //   scene.add(bridgeModel)
  // })
  console.log('[BridgeViewer] Three.js placeholder - 需引入 Three.js 和 bridge.glb 模型')
}

function animate() {
  animationId = requestAnimationFrame(animate)
  // TODO: 渲染循环
  // renderer.render(scene, camera)
}

function onResize() {
  // TODO: 响应窗口大小变化
}

// 根据传感器数据更新构件颜色
watch(() => store.sensorData, (data) => {
  if (!bridgeModel) return
  data.forEach(sensor => {
    const color = getHealthColor(sensor)
    // TODO: 更新对应构件的材质颜色
    // const part = bridgeModel.getObjectByName(sensor.position)
    // if (part) part.material.color.set(color)
  })
}, { deep: true })

function getHealthColor(sensor: any): string {
  if (sensor.type === 'strain') {
    if (sensor.value > 600) return '#ff4d4f'
    if (sensor.value > 450) return '#fa8c16'
    if (sensor.value > 300) return '#fadb14'
  }
  if (sensor.type === 'displacement') {
    if (sensor.value > 80) return '#ff4d4f'
    if (sensor.value > 50) return '#fa8c16'
    if (sensor.value > 30) return '#fadb14'
  }
  return '#52c41a'
}

function getSensorClass(sensor: any): string {
  const color = getHealthColor(sensor)
  if (color === '#ff4d4f') return 'danger'
  if (color === '#fa8c16') return 'warning'
  if (color === '#fadb14') return 'caution'
  return 'normal'
}

// 传感器在3D视图中的2D投影位置（简化版，实际需3D→2D投影）
function getSensorPosition(sensor: any) {
  const positions: Record<string, { left: string; top: string }> = {
    'S01': { left: '50%', top: '45%' },
    'S02': { left: '30%', top: '50%' },
    'S03': { left: '70%', top: '50%' },
    'S04': { left: '15%', top: '55%' },
    'D01': { left: '50%', top: '40%' },
    'D02': { left: '50%', top: '20%' },
    'A01': { left: '50%', top: '48%' },
    'A02': { left: '40%', top: '25%' },
    'T01': { left: '50%', top: '55%' },
  }
  return positions[sensor.sensor_id] || { left: '50%', top: '50%' }
}
</script>

<style scoped>
.bridge-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  background: linear-gradient(180deg, #0a1628 0%, #1a2a4a 100%);
  overflow: hidden;
}

canvas {
  width: 100%;
  height: 100%;
}

.viewer-overlay {
  position: absolute;
  z-index: 10;
  pointer-events: none;
}

.top-left {
  top: 16px;
  left: 16px;
}

.bottom-right {
  bottom: 16px;
  right: 16px;
}

.info-badge {
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  backdrop-filter: blur(10px);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.dot.green { background: #52c41a; box-shadow: 0 0 6px #52c41a; }
.dot.red { background: #ff4d4f; box-shadow: 0 0 6px #ff4d4f; }

.legend {
  background: rgba(0, 0, 0, 0.5);
  padding: 10px 14px;
  border-radius: 8px;
  backdrop-filter: blur(10px);
  pointer-events: auto;
}
.legend-item {
  color: #ccc;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
}
.swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}
.swatch.green { background: #52c41a; }
.swatch.yellow { background: #fadb14; }
.swatch.orange { background: #fa8c16; }
.swatch.red { background: #ff4d4f; }

.sensor-label {
  position: absolute;
  z-index: 5;
  transform: translate(-50%, -50%);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  transition: transform 0.2s;
}
.sensor-label:hover {
  transform: translate(-50%, -50%) scale(1.2);
}
.label-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #fff;
}
.normal .label-dot { background: #52c41a; }
.caution .label-dot { background: #fadb14; }
.warning .label-dot { background: #fa8c16; }
.danger .label-dot { background: #ff4d4f; animation: blink 0.8s infinite; }
.label-text {
  font-size: 10px;
  color: #fff;
  text-shadow: 0 0 4px rgba(0,0,0,0.8);
  white-space: nowrap;
}
.label-value {
  font-size: 11px;
  font-weight: bold;
  color: #fff;
  text-shadow: 0 0 4px rgba(0,0,0,0.8);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
