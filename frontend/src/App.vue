<template>
  <div class="app">
    <!-- 顶部标题栏 -->
    <header class="topbar">
      <div class="title">
        <span class="icon">🌉</span>
        <span class="main">桥梁健康监测数字孪生平台</span>
        <span class="sub">Bridge Health Monitoring Digital Twin Platform</span>
      </div>
      <div class="status-bar">
        <span class="conn" :class="{ on: connected, replay: replayMode }">
          <span class="dot"></span>{{ replayMode ? '⏯ 历史回放中' : (connected ? '实时连接' : '连接断开') }}
        </span>
        <span class="time">{{ now }}</span>
      </div>
    </header>

    <!-- 主体 -->
    <div class="body">
      <!-- 左侧 3D 视图 -->
      <div class="left-panel">
        <div class="panel-title">
          🗺️ 桥梁三维视图
          <span class="view-tip">鼠标拖拽旋转 · 滚轮缩放 · 右键平移</span>
        </div>
        <div class="viewer" ref="viewerRef"></div>
        <!-- 点击信息弹窗 -->
        <div class="info-popup" v-if="popup.show" :style="{ left: popup.x + 'px', top: popup.y + 'px' }">
          <div class="popup-hd">
            <span>{{ popup.title }}</span>
            <button class="popup-close" @click="popup.show = false">×</button>
          </div>
          <div class="popup-body">
            <div v-for="(v, k) in popup.data" :key="k" class="popup-row">
              <span class="pk">{{ k }}</span>
              <span class="pv">{{ v }}</span>
            </div>
          </div>
        </div>
        <!-- 图例 -->
        <div class="legend">
          <span><i class="g"></i>正常</span>
          <span><i class="y"></i>注意</span>
          <span><i class="o"></i>警告</span>
          <span><i class="r"></i>危险</span>
        </div>
      </div>

      <!-- 右侧数据面板 -->
      <div class="right-panel">
        <!-- 历史回放控制条 -->
        <div class="replay-bar" v-if="historyRange.hasData">
          <div class="replay-controls">
            <button class="replay-btn" @click="toggleReplay">
              {{ replayPlaying ? '⏸ 暂停' : '▶ 播放' }}
            </button>
            <select v-model="replaySpeed" class="replay-speed">
              <option :value="1">1x</option>
              <option :value="2">2x</option>
              <option :value="4">4x</option>
              <option :value="8">8x</option>
              <option :value="16">16x</option>
            </select>
            <button class="replay-btn" @click="resetReplay">⏮ 重置</button>
            <span class="replay-time">{{ replayTimeText }}</span>
            <button class="replay-btn" @click="exitReplay" v-if="replayMode">⏹ 退出回放</button>
          </div>
          <input
            type="range"
            class="replay-slider"
            :min="historyRange.start"
            :max="historyRange.end"
            :step="10"
            v-model.number="replayCurrentTs"
            @input="onReplaySeek"
          />
        </div>
        <!-- 统计卡片 -->
        <div class="stats-row">
          <div class="stat-card">
            <div class="num">{{ sensors.length }}</div>
            <div class="lbl">传感器在线</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ totalReadings.toLocaleString() }}</div>
            <div class="lbl">累计读数</div>
          </div>
          <div class="stat-card">
            <div class="num red">{{ alertCount }}</div>
            <div class="lbl">活跃告警</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ uptime }}s</div>
            <div class="lbl">运行时长</div>
          </div>
        </div>

        <!-- 传感器数据 -->
        <div class="data-panel">
          <div class="panel-hd">
            <span>📡 实时传感器数据</span>
            <span class="upd" v-if="lastUpdate">更新于 {{ lastUpdate }}</span>
          </div>
          <div class="sensor-grid">
            <div
              v-for="s in sensors"
              :key="s.sensor_id"
              class="sensor-card"
              :class="getLevel(s)"
              @click="focusSensor(s.sensor_id)"
            >
              <div class="sh">
                <span class="sid">{{ s.sensor_id }}</span>
                <span class="stype">{{ typeName(s.type) }}</span>
              </div>
              <div class="sname">{{ s.name }}</div>
              <div class="sval">{{ s.value.toFixed(2) }}</div>
              <div class="sunit">{{ unitName(s.type) }}</div>
            </div>
          </div>
        </div>

        <!-- 实时趋势图 -->
        <div class="chart-panel">
          <div class="panel-hd">
            <span>📈 实时监测趋势</span>
            <span class="chart-legend">
              <em class="l1"></em>S01跨中应变
              <em class="l2"></em>S03塔顶位移
              <em class="l3"></em>S04拉索振动
            </span>
          </div>
          <div class="chart-container" ref="chartRef"></div>
        </div>

        <!-- 告警列表 -->
        <div class="alert-panel">
          <div class="panel-hd">
            <span>🚨 智能预警</span>
            <span class="alert-badges">
              <em class="r">{{ redCount }}</em>红
              <em class="o">{{ orangeCount }}</em>橙
              <em class="y">{{ yellowCount }}</em>黄
            </span>
          </div>
          <div class="alert-list" v-if="alerts.length">
            <div v-for="a in alerts.slice(0, 6)" :key="a.id" class="alert-item" :class="a.level">
              <span class="ai-icon">{{ levelIcon(a.level) }}</span>
              <div class="ai-body">
                <div class="ai-msg">{{ a.message }}</div>
                <div class="ai-detail">{{ a.sensor_name }} · 当前 {{ a.value.toFixed(2) }} / 阈值 {{ a.threshold }}</div>
              </div>
            </div>
          </div>
          <div class="no-alert" v-else>
            <span>✅</span> 系统运行正常，无告警
          </div>
          <div class="btn-row">
            <button class="btn danger" @click="injectAnomaly('S01')">⚡ 注入异常(S01)</button>
            <button class="btn" @click="resetView">🔄 重置视角</button>
            <button class="btn primary" @click="exportReport">📄 导出报告</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import * as echarts from 'echarts'

interface Sensor {
  sensor_id: string
  name: string
  type: string
  value: number
  timestamp: number
}

interface Alert {
  id: string
  sensor_id: string
  sensor_name: string
  level: string
  message: string
  value: number
  threshold: number
  source: string
  timestamp: number
}

const connected = ref(false)
const sensors = ref<Sensor[]>([])
const alerts = ref<Alert[]>([])
const totalReadings = ref(0)
const now = ref('')
const lastUpdate = ref('')
const startTime = ref(Date.now())
const viewerRef = ref<HTMLDivElement>()
const chartRef = ref<HTMLDivElement>()

// ECharts 变量
let chart: echarts.ECharts | null = null
const historyData: Record<string, { time: string; value: number }[]> = {
  S01: [], S03: [], S04: []
}
const MAX_POINTS = 60

// 点击弹窗
const popup = ref({
  show: false,
  x: 0, y: 0,
  title: '',
  data: {} as Record<string, string | number>
})

// Raycaster
const raycaster = new THREE.Raycaster()
const mouse = new THREE.Vector2()

let ws: WebSocket | null = null
let timer: number | null = null
let reconnectTimer: number | null = null
let animFrame: number = 0

// 历史回放
const historyRange = ref({ start: 0, end: 0, hasData: false })
const replayMode = ref(false)
const replayPlaying = ref(false)
const replaySpeed = ref(4)
const replayCurrentTs = ref(0)
let replayTimer: number | null = null
const replaySnapshot = ref<Record<string, Sensor>>({})
const replayAlerts = ref<Alert[]>([])

const replayTimeText = computed(() => {
  if (!replayCurrentTs.value) return '--:--:--'
  const d = new Date(replayCurrentTs.value * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
})

// Three.js 变量
let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer
let controls: OrbitControls
let sensorMeshes: Record<string, THREE.Mesh> = {}
let partMeshes: Record<string, THREE.Mesh> = {}
let bridgeModel: THREE.Object3D | null = null
const sensorColors = {
  normal: new THREE.Color(0x52c41a),
  caution: new THREE.Color(0xfadb14),
  warning: new THREE.Color(0xfa8c16),
  danger: new THREE.Color(0xff4d4f)
}

const uptime = computed(() => Math.floor((Date.now() - startTime.value) / 1000))
const alertCount = computed(() => alerts.value.length)
const redCount = computed(() => alerts.value.filter(a => a.level === 'red').length)
const orangeCount = computed(() => alerts.value.filter(a => a.level === 'orange').length)
const yellowCount = computed(() => alerts.value.filter(a => a.level === 'yellow').length)

// ====== WebSocket ======
function connect() {
  ws = new WebSocket('ws://127.0.0.1:8000/ws/live')
  ws.onopen = () => { connected.value = true }
  ws.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      if (d.type === 'sensor_update') {
        // 回放模式下不更新实时数据，避免覆盖回放内容
        if (replayMode.value) return
        sensors.value = d.sensors || []
        alerts.value = d.alerts || []
        if (d.stats) totalReadings.value = d.stats.total_readings || 0
        lastUpdate.value = new Date().toLocaleTimeString()
        updateSensorColors()
        updateChartData(d.sensors || [])
      }
    } catch {}
  }
  ws.onclose = () => {
    connected.value = false
    reconnectTimer = window.setTimeout(connect, 3000)
  }
  ws.onerror = () => { connected.value = false }
}

function tick() { now.value = new Date().toLocaleString('zh-CN') }

async function injectAnomaly(id: string) {
  try {
    await fetch(`http://127.0.0.1:8000/api/analysis/inject-anomaly?sensor_id=${id}`, { method: 'POST' })
  } catch {}
}

function resetView() {
  camera.position.set(150, 80, 200)
  controls.target.set(0, 15, 0)
  controls.update()
}

function focusSensor(id: string) {
  const mesh = sensorMeshes[id]
  if (mesh) {
    controls.target.copy(mesh.position)
    controls.update()
  }
}

// ====== 工具函数 ======
function typeName(t: string) {
  return { strain: '应变', displacement: '位移', acceleration: '加速度', temperature: '温度' }[t] || t
}
function unitName(t: string) {
  return { strain: 'με', displacement: 'mm', acceleration: 'm/s²', temperature: '°C' }[t] || ''
}

function getLevel(s: Sensor): string {
  if (s.type === 'strain') {
    if (s.value > 600) return 'danger'
    if (s.value > 450) return 'warning'
    if (s.value > 300) return 'caution'
  } else if (s.type === 'displacement') {
    if (s.value > 80) return 'danger'
    if (s.value > 50) return 'warning'
    if (s.value > 30) return 'caution'
  } else if (s.type === 'acceleration') {
    if (s.value > 5) return 'danger'
    if (s.value > 3.5) return 'warning'
    if (s.value > 2) return 'caution'
  }
  return 'normal'
}

function levelIcon(lv: string) {
  return { red: '🔴', orange: '🟠', yellow: '🟡' }[lv] || '🟢'
}

function getLevelColor(s: Sensor): THREE.Color {
  return sensorColors[getLevel(s) as keyof typeof sensorColors] || sensorColors.normal
}

function updateSensorColors() {
  sensors.value.forEach(s => {
    const mesh = sensorMeshes[s.sensor_id]
    if (mesh) {
      const mat = mesh.material as THREE.MeshStandardMaterial
      mat.color.copy(getLevelColor(s))
      mat.emissive.copy(getLevelColor(s)).multiplyScalar(0.3)
    }
  })
}

// ====== ECharts 图表 ======
function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  const option = {
    backgroundColor: 'transparent',
    grid: { top: 30, right: 15, bottom: 25, left: 45 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22,27,34,0.95)',
      borderColor: '#30363d',
      textStyle: { color: '#c9d1d9', fontSize: 11 }
    },
    legend: { show: false },
    xAxis: {
      type: 'category',
      data: [],
      axisLine: { lineStyle: { color: '#30363d' } },
      axisLabel: { color: '#8b949e', fontSize: 9 },
      splitLine: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        name: '应变/位移',
        nameTextStyle: { color: '#8b949e', fontSize: 9 },
        axisLine: { show: false },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } }
      },
      {
        type: 'value',
        name: '加速度',
        nameTextStyle: { color: '#8b949e', fontSize: 9 },
        axisLine: { show: false },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: 'S01跨中应变',
        type: 'line',
        yAxisIndex: 0,
        data: [],
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#58a6ff', width: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(88,166,255,0.3)' },
          { offset: 1, color: 'rgba(88,166,255,0)' }
        ])}
      },
      {
        name: 'S03塔顶位移',
        type: 'line',
        yAxisIndex: 0,
        data: [],
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f778ba', width: 2 }
      },
      {
        name: 'S04拉索振动',
        type: 'line',
        yAxisIndex: 1,
        data: [],
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#3fb950', width: 2 }
      }
    ]
  }
  chart.setOption(option)
}

function updateChartData(sensorList: Sensor[]) {
  if (!chart) return
  const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })

  const s01 = sensorList.find(s => s.sensor_id === 'S01')
  const s03 = sensorList.find(s => s.sensor_id === 'S03')
  const s04 = sensorList.find(s => s.sensor_id === 'S04')

  if (s01) {
    historyData.S01.push({ time: now, value: s01.value })
    if (historyData.S01.length > MAX_POINTS) historyData.S01.shift()
  }
  if (s03) {
    historyData.S03.push({ time: now, value: s03.value })
    if (historyData.S03.length > MAX_POINTS) historyData.S03.shift()
  }
  if (s04) {
    historyData.S04.push({ time: now, value: s04.value })
    if (historyData.S04.length > MAX_POINTS) historyData.S04.shift()
  }

  chart.setOption({
    xAxis: { data: historyData.S01.map(d => d.time) },
    series: [
      { data: historyData.S01.map(d => d.value) },
      { data: historyData.S03.map(d => d.value) },
      { data: historyData.S04.map(d => d.value) }
    ]
  })
}

// ====== Three.js 场景构建 ======
function initThree() {
  const container = viewerRef.value!
  const w = container.clientWidth
  const h = container.clientHeight

  // 场景
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0a1628)
  scene.fog = new THREE.Fog(0x0a1628, 150, 350)

  // 相机
  camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 1000)
  camera.position.set(150, 80, 200)

  // 渲染器
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  container.appendChild(renderer.domElement)

  // 控制器
  controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, 15, 0)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.maxPolarAngle = Math.PI / 2.1
  controls.minDistance = 30
  controls.maxDistance = 400
  controls.update()

  // 灯光
  const ambient = new THREE.AmbientLight(0x404060, 0.6)
  scene.add(ambient)

  const sun = new THREE.DirectionalLight(0xffffff, 1.2)
  sun.position.set(50, 80, 60)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  sun.shadow.camera.left = -100
  sun.shadow.camera.right = 100
  sun.shadow.camera.top = 80
  sun.shadow.camera.bottom = -80
  scene.add(sun)

  const fill = new THREE.DirectionalLight(0x6688cc, 0.3)
  fill.position.set(-40, 30, -50)
  scene.add(fill)

  // 水面
  const waterGeo = new THREE.PlaneGeometry(400, 200)
  const waterMat = new THREE.MeshStandardMaterial({
    color: 0x0d2840,
    metalness: 0.8,
    roughness: 0.2,
    transparent: true,
    opacity: 0.85
  })
  const water = new THREE.Mesh(waterGeo, waterMat)
  water.rotation.x = -Math.PI / 2
  water.position.y = -2
  water.receiveShadow = true
  water.raycast = () => {}  // 水面不参与点击检测
  scene.add(water)

  // 地面/岸
  const groundGeo = new THREE.PlaneGeometry(400, 200)
  const groundMat = new THREE.MeshStandardMaterial({ color: 0x1a2a1a, roughness: 0.9 })
  const ground = new THREE.Mesh(groundGeo, groundMat)
  ground.rotation.x = -Math.PI / 2
  ground.position.y = -2.1
  ground.receiveShadow = true
  ground.raycast = () => {}  // 地面不参与点击检测
  scene.add(ground)

  // ====== 加载桥梁模型 ======
  // 优先加载glb真实模型，加载失败则回退到程序化生成
  const gltfLoader = new GLTFLoader()
  gltfLoader.load(
    '/models/huihe_bridge.glb',
    (gltf) => {
      console.log('✅ 浍河大桥GLB模型加载成功')
      const model = gltf.scene
      bridgeModel = model

      // 自动计算模型包围盒，调整大小和位置
      const box = new THREE.Box3().setFromObject(model)
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())

      // 缩放到合适大小（让桥梁长度约240单位，和原来的程序化桥梁一致）
      const scale = 240 / size.x
      model.scale.setScalar(scale)

      // 居中并放到地面上
      model.position.x = -center.x * scale
      model.position.y = -box.min.y * scale
      model.position.z = -center.z * scale

      // 开启阴影
      model.traverse((child: any) => {
        if (child.isMesh) {
          child.castShadow = true
          child.receiveShadow = true
          // 给构件命名，方便点击识别
          if (!child.name || child.name === 'Mesh') {
            child.name = 'bridge_part'
          }
        }
      })

      scene.add(model)

      // ====== 添加斜拉索（和Revit模型位置对齐）======
      const cableMat = new THREE.MeshStandardMaterial({
        color: 0x444444,
        metalness: 0.8,
        roughness: 0.3
      })
      const towerXs = [-60, 60]
      towerXs.forEach(tx => {
        const isLeft = tx < 0
        // 主跨侧6根
        for (let i = 0; i < 6; i++) {
          const deckX = isLeft ? tx - (i+1)*10 : tx + (i+1)*10
          const towerZ = 20 + 50 - 5 - i*3
          const start = new THREE.Vector3(tx, towerZ, 0)
          const end = new THREE.Vector3(deckX, 20, 0)
          const dir = end.clone().sub(start)
          const len = dir.length()
          const cable = new THREE.Mesh(
            new THREE.CylinderGeometry(0.15, 0.15, len, 8),
            cableMat
          )
          cable.position.copy(start.clone().add(end).multiplyScalar(0.5))
          cable.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            dir.normalize()
          )
          cable.name = '拉索-' + (isLeft ? 'L' : 'R') + (i+1).toString().padStart(2, '0')
          cable.castShadow = true
          model.add(cable)
        }
        // 边跨侧6根
        for (let i = 0; i < 6; i++) {
          const deckX = isLeft ? tx + (i+1)*10 : tx - (i+1)*10
          const towerZ = 20 + 50 - 5 - i*3
          const start = new THREE.Vector3(tx, towerZ, 0)
          const end = new THREE.Vector3(deckX, 20, 0)
          const dir = end.clone().sub(start)
          const len = dir.length()
          const cable = new THREE.Mesh(
            new THREE.CylinderGeometry(0.15, 0.15, len, 8),
            cableMat
          )
          cable.position.copy(start.clone().add(end).multiplyScalar(0.5))
          cable.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            dir.normalize()
          )
          cable.name = '拉索-' + (isLeft ? 'L' : 'R') + (i+7).toString().padStart(2, '0')
          cable.castShadow = true
          model.add(cable)
        }
      })

      // 调整相机初始位置
      camera.position.set(150, 80, 200)
      controls.target.set(0, 15, 0)
      controls.update()
    },
    (progress) => {
      // 加载进度
      if (progress.total > 0) {
        const percent = Math.round(progress.loaded / progress.total * 100)
        console.log(`模型加载中: ${percent}%`)
      }
    },
    (err) => {
      console.log('⚠️ GLB模型未找到，使用程序化生成桥梁', err)
      buildCableStayedBridge()
    }
  )

  // 网格辅助
  const grid = new THREE.GridHelper(300, 60, 0x1a3a5c, 0x0d2233)
  grid.position.y = -1.9
  grid.raycast = () => {}  // 网格不参与点击检测
  scene.add(grid)

  // 动画循环
  animate()

  // 窗口大小
  window.addEventListener('resize', onResize)

  // 点击事件
  renderer.domElement.addEventListener('click', onCanvasClick)
}

function buildCableStayedBridge() {
  const bridgeMat = new THREE.MeshStandardMaterial({ color: 0x6b7280, metalness: 0.6, roughness: 0.4 })
  const deckMat = new THREE.MeshStandardMaterial({ color: 0x4a5568, metalness: 0.5, roughness: 0.5 })
  const cableMat = new THREE.MeshStandardMaterial({ color: 0x9ca3af, metalness: 0.7, roughness: 0.3 })
  const concreteMat = new THREE.MeshStandardMaterial({ color: 0x78716c, roughness: 0.8 })

  // 尺寸参数
  const towerH = 50      // 索塔高度
  const towerW = 4       // 索塔宽度
  const deckW = 14       // 桥面宽度
  const deckH = 2.5      // 桥面厚度
  const span = 120       // 主跨长度
  const sideSpan = 60    // 边跨长度
  const totalLen = span + sideSpan * 2  // 总长240

  // ===== 索塔（两座H型索塔）=====
  for (const x of [-span/2, span/2]) {
    const towerGroup = new THREE.Group()
    towerGroup.name = x < 0 ? 'tower_left' : 'tower_right'

    // 两根塔柱
    for (const z of [-deckW/2 - 1, deckW/2 + 1]) {
      const leg = new THREE.Mesh(
        new THREE.BoxGeometry(towerW, towerH, towerW),
        bridgeMat
      )
      leg.position.set(0, towerH/2, z)
      leg.castShadow = true
      leg.receiveShadow = true
      towerGroup.add(leg)
    }
    // 上横梁
    const topBeam = new THREE.Mesh(
      new THREE.BoxGeometry(towerW * 1.5, 2, deckW + 4),
      bridgeMat
    )
    topBeam.position.set(0, towerH - 3, 0)
    topBeam.castShadow = true
    towerGroup.add(topBeam)
    // 下横梁（桥面处）
    const botBeam = new THREE.Mesh(
      new THREE.BoxGeometry(towerW * 1.5, 2, deckW + 4),
      bridgeMat
    )
    botBeam.position.set(0, deckH/2, 0)
    botBeam.castShadow = true
    towerGroup.add(botBeam)

    towerGroup.position.set(x, 0, 0)
    scene.add(towerGroup)
    partMeshes[towerGroup.name] = towerGroup as unknown as THREE.Mesh
  }

  // ===== 主梁（桥面）=====
  const deck = new THREE.Mesh(
    new THREE.BoxGeometry(totalLen, deckH, deckW),
    deckMat
  )
  deck.position.set(0, deckH/2, 0)
  deck.castShadow = true
  deck.receiveShadow = true
  deck.name = 'deck'
  scene.add(deck)
  partMeshes['deck'] = deck

  // 桥面标线
  const lineMat = new THREE.MeshStandardMaterial({ color: 0xfbbf24, roughness: 0.6 })
  for (let i = -totalLen/2 + 5; i < totalLen/2; i += 10) {
    const line = new THREE.Mesh(
      new THREE.BoxGeometry(4, 0.05, 0.3),
      lineMat
    )
    line.position.set(i, deckH + 0.03, 0)
    scene.add(line)
  }

  // ===== 桥墩 =====
  for (const x of [-span/2 - sideSpan, -span/2, span/2, span/2 + sideSpan]) {
    const pier = new THREE.Mesh(
      new THREE.BoxGeometry(6, 8, deckW + 2),
      concreteMat
    )
    pier.position.set(x, -4, 0)
    pier.castShadow = true
    pier.receiveShadow = true
    scene.add(pier)
  }

  // ===== 拉索（扇形布置）=====
  const cableCount = 12  // 每侧每塔6对
  const cableRadius = 0.15
  for (const tx of [-span/2, span/2]) {
    for (let i = 1; i <= cableCount/2; i++) {
      const ratio = i / (cableCount/2 + 1)
      // 向跨中方向
      const anchorX1 = tx + (tx < 0 ? ratio * span/2 : -ratio * span/2)
      const topY = towerH - 5 - ratio * (towerH - 15)
      createCable(tx, topY, anchorX1, deckH, cableRadius, cableMat)
      // 向边跨方向
      const anchorX2 = tx + (tx < 0 ? -ratio * sideSpan : ratio * sideSpan)
      createCable(tx, topY, anchorX2, deckH, cableRadius, cableMat)
    }
  }

  // ===== 传感器标记 =====
  createSensors()
}

function createCable(x1: number, y1: number, x2: number, y2: number, r: number, mat: THREE.Material) {
  const start = new THREE.Vector3(x1, y1, 0)
  const end = new THREE.Vector3(x2, y2, 0)
  const len = start.distanceTo(end)
  const geo = new THREE.CylinderGeometry(r, r, len, 6)
  const mesh = new THREE.Mesh(geo, mat)
  mesh.position.copy(start.clone().add(end).multiplyScalar(0.5))
  mesh.position.z = 0
  const dir = end.clone().sub(start).normalize()
  const axis = new THREE.Vector3(0, 1, 0)
  mesh.quaternion.setFromUnitVectors(axis, dir)
  mesh.castShadow = true
  scene.add(mesh)
}

function createSensors() {
  // 8个传感器位置（对应后端simulator的S01-S08）
  const sensorPositions: Record<string, { x: number; y: number; z: number }> = {
    S01: { x: 0, y: 4, z: 0 },           // 主跨跨中-应变
    S02: { x: -30, y: 4, z: 0 },         // 主跨1/4-应变
    S03: { x: 60, y: 50, z: 0 },         // 索塔顶部-位移（右塔）
    S04: { x: -45, y: 20, z: 0 },        // 拉索L01-加速度
    S05: { x: 0, y: 3.5, z: 5 },         // 主跨跨中-挠度
    S06: { x: 60, y: 2, z: 0 },          // 索塔底部-应变（右塔底）
    S07: { x: 45, y: 20, z: 0 },         // 拉索L02-加速度
    S08: { x: 0, y: 5, z: -6 },          // 桥面温度
  }

  const sensorGeo = new THREE.SphereGeometry(1.2, 16, 16)

  Object.entries(sensorPositions).forEach(([id, pos]) => {
    const mat = new THREE.MeshStandardMaterial({
      color: 0x52c41a,
      emissive: 0x52c41a,
      emissiveIntensity: 0.3,
      metalness: 0.3,
      roughness: 0.5
    })
    const mesh = new THREE.Mesh(sensorGeo, mat)
    mesh.position.set(pos.x, pos.y, pos.z)
    mesh.castShadow = true
    mesh.name = `sensor_${id}`
    scene.add(mesh)
    sensorMeshes[id] = mesh

    // 传感器脉冲光环
    const ringGeo = new THREE.RingGeometry(1.5, 2.2, 24)
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x52c41a,
      transparent: true,
      opacity: 0.5,
      side: THREE.DoubleSide
    })
    const ring = new THREE.Mesh(ringGeo, ringMat)
    ring.position.copy(mesh.position)
    ring.lookAt(camera.position)
    ring.name = `ring_${id}`
    scene.add(ring)
  })
}

function animate() {
  animFrame = requestAnimationFrame(animate)
  controls.update()

  // 传感器脉冲动画
  const t = Date.now() * 0.003
  Object.entries(sensorMeshes).forEach(([id, mesh]) => {
    const ring = scene.getObjectByName(`ring_${id}`) as THREE.Mesh
    if (ring) {
      const scale = 1 + Math.sin(t + id.charCodeAt(2)) * 0.3
      ring.scale.set(scale, scale, 1)
      ring.lookAt(camera.position)
      const mat = ring.material as THREE.MeshBasicMaterial
      const s = sensors.value.find(s => s.sensor_id === id)
      if (s) {
        mat.color.copy(getLevelColor(s))
        if (getLevel(s) === 'danger') {
          mat.opacity = 0.3 + Math.sin(t * 3) * 0.3
        } else {
          mat.opacity = 0.4
        }
      }
    }
  })

  renderer.render(scene, camera)
}

function onResize() {
  if (!viewerRef.value) return
  const w = viewerRef.value.clientWidth
  const h = viewerRef.value.clientHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
  if (chart) chart.resize()
}

function onCanvasClick(event: MouseEvent) {
  if (!viewerRef.value) return
  const viewerEl = viewerRef.value
  const parentEl = viewerEl.parentElement
  if (!parentEl) return

  const rect = viewerEl.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(mouse, camera)
  const allMeshes: THREE.Object3D[] = []
  Object.values(sensorMeshes).forEach(m => allMeshes.push(m))
  Object.values(partMeshes).forEach(m => allMeshes.push(m))
  if (bridgeModel) allMeshes.push(bridgeModel)

  const intersects = raycaster.intersectObjects(allMeshes, true)
  if (intersects.length > 0) {
    const obj = intersects[0].object
    let clickedObj: THREE.Object3D | null = obj
    let sensorId = ''
    let partName = ''
    let partNameZh = ''

    while (clickedObj) {
      const name = clickedObj.name || ''
      if (name.startsWith('sensor_')) {
        sensorId = name.replace('sensor_', '')
        break
      }
      if (['tower_left', 'tower_right', 'deck'].includes(name)) {
        partName = name
        break
      }
      // 识别Revit导出的中文构件名
      if (name.includes('索塔')) {
        partName = 'tower'
        partNameZh = name.includes('左') ? '🏗️ 左索塔' : '🏗️ 右索塔'
        break
      }
      if (name.includes('主梁') || name.includes('桥面') || name.includes('箱梁')) {
        partName = 'deck'
        partNameZh = '🛣️ 主梁/桥面'
        break
      }
      if (name.includes('桥墩')) {
        partName = 'pier'
        partNameZh = '🏛️ ' + name
        break
      }
      if (name.includes('承台')) {
        partName = 'cap'
        partNameZh = '🧱 ' + name
        break
      }
      if (name.includes('拉索')) {
        partName = 'cable'
        partNameZh = '🔗 ' + name
        break
      }
      if (name.includes('传感器')) {
        // 从中文名提取传感器ID，比如"传感器-S01-应变计"
        const match = name.match(/S\d+/)
        if (match) sensorId = match[0]
        break
      }
      clickedObj = clickedObj.parent
    }

    // 弹窗位置相对于left-panel（弹窗是viewer的兄弟元素）
    const parentRect = parentEl.getBoundingClientRect()
    const popupX = event.clientX - parentRect.left + 10
    const popupY = event.clientY - parentRect.top - 10

    if (sensorId) {
      const s = sensors.value.find(x => x.sensor_id === sensorId)
      if (s) {
        popup.value = {
          show: true,
          x: popupX,
          y: popupY,
          title: `📡 ${s.name} (${s.sensor_id})`,
          data: {
            '传感器类型': typeName(s.type),
            '当前读数': `${s.value.toFixed(2)} ${unitName(s.type)}`,
            '健康状态': getLevelText(getLevel(s)),
            '更新时间': new Date(s.timestamp * 1000).toLocaleTimeString('zh-CN')
          }
        }
      }
    } else if (partName) {
      let title = ''
      let partType = ''
      let relatedSensors = ''

      if (partNameZh) {
        title = partNameZh
      } else {
        const names: Record<string, string> = {
          tower_left: '🏗️ 左索塔',
          tower_right: '🏗️ 右索塔',
          deck: '🛣️ 主梁/桥面'
        }
        title = names[partName] || partName
      }

      if (partName === 'tower' || partName.startsWith('tower')) {
        partType = 'H型钢筋混凝土索塔，高50m'
        relatedSensors = partNameZh?.includes('右') ? 'S03（塔顶位移）、S06（塔底应变）' : 'S04（拉索振动）'
      } else if (partName === 'deck') {
        partType = '单箱单室混凝土箱梁，梁高2.5m，宽14m'
        relatedSensors = 'S01（跨中应变）、S02（1/4跨应变）、S05（跨中挠度）、S08（温度）'
      } else if (partName === 'pier') {
        partType = '钢筋混凝土桥墩，直径2.5m'
        relatedSensors = '无直接监测传感器'
      } else if (partName === 'cap') {
        partType = '钢筋混凝土承台，12m×12m×3.5m'
        relatedSensors = '无直接监测传感器'
      } else if (partName === 'cable') {
        partType = '高强度平行钢丝拉索，直径150mm'
        relatedSensors = 'S04/S07（拉索振动加速度）'
      } else {
        partType = '桥梁结构构件'
        relatedSensors = '/'
      }

      popup.value = {
        show: true,
        x: popupX,
        y: popupY,
        title: title,
        data: {
          '构件类型': partType,
          '健康状态': '✅ 正常',
          '关联传感器': relatedSensors
        }
      }
    }
  } else {
    popup.value.show = false
  }
}

function getLevelText(level: string): string {
  return { normal: '✅ 正常', caution: '🟡 注意', warning: '🟠 警告', danger: '🔴 危险' }[level] || '未知'
}

// ====== 历史回放 ======
async function loadHistoryRange() {
  try {
    const res = await fetch('http://127.0.0.1:8000/api/sensors/history/timerange')
    const data = await res.json()
    if (data.has_data) {
      historyRange.value = { start: data.start, end: data.end, hasData: true }
      replayCurrentTs.value = data.start
    }
  } catch (e) {
    console.log('无历史数据')
  }
}

function toggleReplay() {
  if (!historyRange.value.hasData) return
  if (!replayMode.value) {
    replayMode.value = true
    replayPlaying.value = true
    // 清空图表，准备回放
    historyData.S01 = []
    historyData.S03 = []
    historyData.S04 = []
    runReplay()
  } else {
    replayPlaying.value = !replayPlaying.value
    if (replayPlaying.value) runReplay()
    else if (replayTimer) { clearInterval(replayTimer); replayTimer = null }
  }
}

function runReplay() {
  if (replayTimer) clearInterval(replayTimer)
  replayTimer = window.setInterval(async () => {
    if (!replayPlaying.value) return
    // 每次前进 10秒 * 倍速
    replayCurrentTs.value += 10 * replaySpeed.value
    if (replayCurrentTs.value >= historyRange.value.end) {
      replayCurrentTs.value = historyRange.value.end
      replayPlaying.value = false
      if (replayTimer) { clearInterval(replayTimer); replayTimer = null }
    }
    await loadReplaySnapshot()
  }, 500)
}

async function loadReplaySnapshot() {
  try {
    const res = await fetch(`http://127.0.0.1:8000/api/sensors/history/snapshot?ts=${replayCurrentTs.value}`)
    replaySnapshot.value = await res.json()
    // 更新传感器显示
    const snapshotArr = Object.values(replaySnapshot.value) as Sensor[]
    if (snapshotArr.length) {
      sensors.value = snapshotArr
      updateSensorColors()
      // 更新图表
      updateReplayChart()
    }
    // 加载该时间点前1小时内的告警
    const res2 = await fetch(`http://127.0.0.1:8000/api/sensors/history/alerts?start=${replayCurrentTs.value - 3600}&end=${replayCurrentTs.value}`)
    const aData = await res2.json()
    replayAlerts.value = aData.alerts || []
    alerts.value = replayAlerts.value
  } catch (e) {
    console.error('回放加载失败', e)
  }
}

function updateReplayChart() {
  if (!chart) return
  // 取S01/S03/S04在回放时间点的值
  const s01 = replaySnapshot.value['S01']
  const s03 = replaySnapshot.value['S03']
  const s04 = replaySnapshot.value['S04']
  const time = new Date(replayCurrentTs.value * 1000).toLocaleTimeString('zh-CN', { hour12: false })

  if (s01) {
    historyData.S01.push({ time, value: s01.value })
    if (historyData.S01.length > MAX_POINTS) historyData.S01.shift()
  }
  if (s03) {
    historyData.S03.push({ time, value: s03.value })
    if (historyData.S03.length > MAX_POINTS) historyData.S03.shift()
  }
  if (s04) {
    historyData.S04.push({ time, value: s04.value })
    if (historyData.S04.length > MAX_POINTS) historyData.S04.shift()
  }
  chart.setOption({
    xAxis: { data: historyData.S01.map(d => d.time) },
    series: [
      { data: historyData.S01.map(d => d.value) },
      { data: historyData.S03.map(d => d.value) },
      { data: historyData.S04.map(d => d.value) }
    ]
  })
}

function onReplaySeek() {
  if (replayPlaying.value) return
  replayMode.value = true
  loadReplaySnapshot()
}

function resetReplay() {
  replayCurrentTs.value = historyRange.value.start
  historyData.S01 = []
  historyData.S03 = []
  historyData.S04 = []
  loadReplaySnapshot()
}

function exitReplay() {
  replayMode.value = false
  replayPlaying.value = false
  if (replayTimer) { clearInterval(replayTimer); replayTimer = null }
  // 关闭旧连接后重新连接实时数据
  if (ws) { ws.onclose = null; ws.close(); ws = null }
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  historyData.S01 = []
  historyData.S03 = []
  historyData.S04 = []
  connect()
}

// ====== 导出报告 ======
function exportReport() {
  window.open('http://127.0.0.1:8000/api/analysis/report?hours=24', '_blank')
}

// ====== 生命周期 ======
onMounted(async () => {
  await nextTick()
  initThree()
  initChart()
  connect()
  loadHistoryRange()
  tick()
  timer = window.setInterval(tick, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (ws) ws.close()
  cancelAnimationFrame(animFrame)
  window.removeEventListener('resize', onResize)
  if (renderer) renderer.dispose()
  if (chart) chart.dispose()
})
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { width: 100%; height: 100%; overflow: hidden; }
body { font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif; background: #0d1117; color: #c9d1d9; }

.app { display: flex; flex-direction: column; height: 100vh; }

/* 顶部栏 */
.topbar {
  height: 50px; background: #161b22; border-bottom: 1px solid #30363d;
  display: flex; justify-content: space-between; align-items: center; padding: 0 20px; flex-shrink: 0;
}
.title { display: flex; align-items: baseline; gap: 10px; }
.icon { font-size: 22px; }
.main { font-size: 17px; font-weight: 700; color: #f0f6fc; }
.sub { font-size: 11px; color: #8b949e; }
.status-bar { display: flex; align-items: center; gap: 16px; font-size: 12px; }
.conn { display: flex; align-items: center; gap: 6px; color: #8b949e; }
.conn .dot { width: 8px; height: 8px; border-radius: 50%; background: #484f58; }
.conn.on .dot { background: #52c41a; box-shadow: 0 0 6px #52c41a; }
.time { color: #8b949e; font-family: Consolas, monospace; }

/* 主体 */
.body { flex: 1; display: flex; overflow: hidden; }
.left-panel { flex: 58; border-right: 1px solid #30363d; display: flex; flex-direction: column; position: relative; }
.right-panel { flex: 42; display: flex; flex-direction: column; overflow-y: auto; padding: 12px; gap: 12px; }

.panel-title {
  padding: 10px 16px; font-size: 14px; font-weight: 600; color: #f0f6fc;
  border-bottom: 1px solid #30363d; background: #161b22;
  display: flex; justify-content: space-between; align-items: center;
}
.view-tip { font-size: 11px; font-weight: 400; color: #8b949e; }

/* 3D 视图 */
.viewer { flex: 1; position: relative; min-height: 0; overflow: hidden; z-index: 1; }
.viewer canvas { display: block; position: absolute; top: 0; left: 0; width: 100% !important; height: 100% !important; }

/* 图例 */
.legend {
  position: absolute; top: 50px; right: 16px; z-index: 10;
  background: rgba(0,0,0,0.5); padding: 10px 14px; border-radius: 8px;
  display: flex; gap: 12px; font-size: 12px; color: #ccc;
  backdrop-filter: blur(10px);
}
.legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 4px; vertical-align: middle; }
.legend .g { background: #52c41a; }
.legend .y { background: #fadb14; }
.legend .o { background: #fa8c16; }
.legend .r { background: #ff4d4f; }

/* 历史回放控制条 */
.replay-bar {
  background: #161b22;
  border-top: 1px solid #30363d;
  padding: 10px 16px;
  flex-shrink: 0;
  position: relative;
  z-index: 100;
}
.replay-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.replay-btn {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 5px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.replay-btn:hover { background: #30363d; border-color: #58a6ff; }
.replay-speed {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 13px;
}
.replay-time {
  color: #58a6ff;
  font-size: 13px;
  font-family: monospace;
  margin-left: auto;
}
.replay-slider {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  background: #21262d;
  border-radius: 3px;
  outline: none;
}
.replay-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #58a6ff;
  cursor: pointer;
}
.btn.primary { background: #238636; border-color: #238636; color: white; }
.btn.primary:hover { background: #2ea043; }

/* 统计卡片 */
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; text-align: center; }
.stat-card .num { font-size: 26px; font-weight: 700; color: #58a6ff; }
.stat-card .num.red { color: #ff4d4f; }
.stat-card .lbl { font-size: 12px; color: #8b949e; margin-top: 4px; }

/* 数据面板 */
.data-panel, .alert-panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
.panel-hd {
  padding: 10px 14px; border-bottom: 1px solid #30363d;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 14px; font-weight: 600; color: #f0f6fc;
}
.upd { font-size: 11px; font-weight: 400; color: #8b949e; }

.sensor-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 10px; }
.sensor-card {
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  padding: 10px; cursor: pointer; transition: all 0.2s;
}
.sensor-card:hover { border-color: #58a6ff; transform: translateY(-1px); }
.sensor-card.caution { border-color: #fadb14; }
.sensor-card.warning { border-color: #fa8c16; }
.sensor-card.danger { border-color: #ff4d4f; animation: pulse 1.5s infinite; }
.sh { display: flex; justify-content: space-between; margin-bottom: 4px; }
.sid { font-size: 11px; color: #58a6ff; font-weight: 600; }
.stype { font-size: 10px; color: #8b949e; background: #21262d; padding: 1px 5px; border-radius: 3px; }
.sname { font-size: 11px; color: #c9d1d9; margin-bottom: 6px; }
.sval { font-size: 20px; font-weight: 700; color: #f0f6fc; }
.sunit { font-size: 10px; color: #8b949e; }

@keyframes pulse {
  0%,100% { box-shadow: 0 0 0 0 rgba(255,77,79,0.4); }
  50% { box-shadow: 0 0 0 6px rgba(255,77,79,0); }
}

/* 告警 */
.alert-list { max-height: 200px; overflow-y: auto; padding: 8px; }
.alert-item { display: flex; gap: 8px; padding: 8px 10px; margin-bottom: 4px; border-radius: 6px; background: #0d1117; border-left: 3px solid #30363d; }
.alert-item.red { border-left-color: #ff4d4f; background: rgba(255,77,79,0.05); }
.alert-item.orange { border-left-color: #fa8c16; background: rgba(250,140,22,0.05); }
.alert-item.yellow { border-left-color: #fadb14; background: rgba(250,219,20,0.05); }
.ai-icon { font-size: 16px; flex-shrink: 0; }
.ai-body { flex: 1; min-width: 0; }
.ai-msg { font-size: 12px; color: #f0f6fc; }
.ai-detail { font-size: 10px; color: #8b949e; margin-top: 2px; }
.no-alert { padding: 30px; text-align: center; color: #8b949e; font-size: 13px; }

.alert-badges { font-size: 11px; font-weight: 400; display: flex; gap: 8px; }
.alert-badges em { font-style: normal; font-weight: 700; margin-right: 2px; }
.alert-badges .r { color: #ff4d4f; }
.alert-badges .o { color: #fa8c16; }
.alert-badges .y { color: #fadb14; }

.btn-row { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid #30363d; }
.btn {
  flex: 1; padding: 8px; background: #21262d; color: #f0f6fc;
  border: 1px solid #30363d; border-radius: 6px; font-size: 12px;
  cursor: pointer; transition: all 0.2s;
}
.btn:hover { background: #30363d; }
.btn.danger:hover { border-color: #ff4d4f; color: #ff4d4f; }

/* 图表面板 */
.chart-panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
.chart-container { height: 180px; padding: 0; }
.chart-legend { font-size: 10px; font-weight: 400; display: flex; gap: 10px; align-items: center; }
.chart-legend em {
  display: inline-block; width: 12px; height: 3px; border-radius: 2px;
  margin-right: 3px; vertical-align: middle;
}
.chart-legend .l1 { background: #58a6ff; }
.chart-legend .l2 { background: #f778ba; }
.chart-legend .l3 { background: #3fb950; }

/* 信息弹窗 */
.info-popup {
  position: absolute; z-index: 100; min-width: 200px;
  background: rgba(22, 27, 34, 0.95); border: 1px solid #30363d;
  border-radius: 8px; backdrop-filter: blur(10px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  animation: popupIn 0.2s ease;
}
@keyframes popupIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}
.popup-hd {
  padding: 8px 12px; border-bottom: 1px solid #30363d;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; font-weight: 600; color: #f0f6fc;
}
.popup-close {
  background: none; border: none; color: #8b949e; font-size: 18px;
  cursor: pointer; padding: 0 4px; line-height: 1;
}
.popup-close:hover { color: #ff4d4f; }
.popup-body { padding: 8px 12px; }
.popup-row {
  display: flex; justify-content: space-between; padding: 4px 0;
  font-size: 12px; gap: 16px;
}
.pk { color: #8b949e; }
.pv { color: #f0f6fc; font-weight: 500; }
</style>
