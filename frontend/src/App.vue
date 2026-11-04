<template>
  <div class="app" :class="'level-' + systemLevel">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 48 48">
            <path d="M5 37h38M13 37V13M35 37V13M13 18l22 19M35 18 13 37M8 31h32" />
          </svg>
        </div>
        <div class="brand-lockup">
        <div class="brand-l1" :title="brandTitle">{{ brandTitle }}</div>
          <div class="brand-l2">STRUCTURAL HEALTH MONITORING</div>
          <div class="brand-l3"><span>MONITOR</span><b>OS</b></div>
        </div>
      </div>

      <div class="topbar-mid" aria-hidden="true">
        <span>SYNTHESIZE SENSOR DATA</span>
        <i></i>
        <span>ANALYZE STRUCTURAL STATE</span>
      </div>

      <div class="topbar-actions">
        <span class="conn" :class="{ on: connected, replay: replayMode }" :title="connectionError || replayError">
          <i></i>{{ replayMode ? 'REPLAY / 历史回放' : connected ? 'LIVE / 实时连接' : 'OFFLINE / 连接断开' }}
        </span>
        <span class="model-ref">MODEL / {{ activeModelLabel }}</span>
        <button class="import-btn" type="button" @click="modelDialogVisible = true">
          <span>导入模型</span>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2v8m0 0 3-3m-3 3L5 7M3 12v2h10v-2" /></svg>
        </button>
        <div class="clock">
          <span>{{ nowDate }}</span>
          <b>{{ nowClock }}</b>
        </div>
      </div>
    </header>

    <main class="stage">
      <div class="viewer" ref="viewerRef"></div>
      <div v-if="sceneError" class="scene-error">
        <span>SCENE PROFILE ERROR</span>
        <strong>{{ sceneError }}</strong>
      </div>
      <div class="stage-grid" aria-hidden="true"></div>
      <i class="corner tl" aria-hidden="true"></i>
      <i class="corner tr" aria-hidden="true"></i>
      <i class="corner bl" aria-hidden="true"></i>
      <i class="corner br" aria-hidden="true"></i>

      <aside class="rail" aria-hidden="true">
        <span class="rail-index">04</span>
        <div class="rail-nodes">
          <span v-for="s in sortedSensors" :key="s.sensor_id" :class="getLevel(s)"></span>
        </div>
        <i class="rail-rule"></i>
        <span class="rail-caption">SECTION 04 · MAIN SPAN</span>
      </aside>

      <div class="stage-title">
        <div class="stage-kicker">LIVE STRUCTURAL MODEL / 实时结构模型</div>
        <h1>{{ stageDisplayName }}<span>{{ stageEnglishName }}</span></h1>
        <div class="stage-sub">{{ stageDescription }}</div>
        <div class="stage-readout">
          <span>RESPONSE {{ pressureField?.max?.toFixed(3) ?? '—' }}</span>
          <span>STATE {{ systemStateEn }}</span>
        </div>
      </div>

      <div class="stage-tools">
        <span class="source-chip">
          {{ activeModelLabel }} · {{ activeProfile?.source?.toUpperCase() || 'NO' }} PROFILE
        </span>
        <button class="tool" type="button" :class="{ active: pressureOverlayEnabled }" @click="pressureOverlayEnabled = !pressureOverlayEnabled">
          <i></i>FIELD MAP
        </button>
        <button class="tool" type="button" @click="resetView">RESET VIEW</button>
      </div>
      <span class="view-hint">DRAG ROTATE · SCROLL ZOOM · RIGHT-DRAG PAN</span>

      <div class="info-popup" v-if="popup.show" :style="{ left: popup.x + 'px', top: popup.y + 'px' }">
        <div class="popup-hd">
          <span>{{ popup.title }}</span>
          <button class="popup-close" type="button" aria-label="关闭" @click="popup.show = false">×</button>
        </div>
        <div class="popup-body">
          <div v-for="(v, k) in popup.data" :key="k" class="popup-row">
            <span class="pk">{{ k }}</span>
            <span class="pv">{{ v }}</span>
          </div>
        </div>
      </div>

      <PressureCloud
        class="stage-pressure"
        :field="pressureField"
        :overlay-enabled="pressureOverlayEnabled"
        @toggle-overlay="pressureOverlayEnabled = !pressureOverlayEnabled"
      />

      <div class="legend" aria-label="状态图例">
        <span><i class="n"></i>NORMAL 正常</span>
        <span><i class="y"></i>CAUTION 注意</span>
        <span><i class="o"></i>WARNING 警告</span>
        <span><i class="r"></i>ALERT 危险</span>
      </div>
    </main>

    <aside class="dossier">
      <div class="dossier-tags">
        <span class="tag-solid">SECTION PROFILE</span>
        <span class="tag-rule">SHM / 04</span>
        <span class="tag-rule">{{ nowDate }}</span>
      </div>

      <div class="dossier-state">
        <span class="micro">SYSTEM STATE / 系统状态</span>
        <div class="state-value"><i class="state-dot"></i><strong>{{ systemStateZh }}</strong></div>
        <span class="state-en">{{ systemStateEn }}</span>
      </div>

      <div class="stat-grid">
        <div class="stat">
          <span class="stat-label">SENSOR NODES</span>
          <span class="stat-value">{{ pad2(onlineSensorCount) }}<small>/{{ pad2(sensors.length) }}</small></span>
          <span class="stat-zh">在线传感器</span>
        </div>
        <div class="stat">
          <span class="stat-label">CUMULATIVE READS</span>
          <span class="stat-value">{{ totalReadings.toLocaleString() }}</span>
          <span class="stat-zh">累计读数</span>
        </div>
        <div class="stat">
          <span class="stat-label">RECENT ALERTS</span>
          <span class="stat-value alert-number">{{ pad2(alertCount) }}</span>
          <span class="stat-zh">近期告警</span>
        </div>
        <div class="stat">
          <span class="stat-label">SESSION UPTIME</span>
          <span class="stat-value">{{ uptimeText }}</span>
          <span class="stat-zh">运行时长</span>
        </div>
      </div>

      <section class="block sensors-block">
        <header class="block-head">
          <span class="code">01</span>
          <h2>LIVE SENSOR ARRAY</h2>
          <span class="note">实时测点</span>
        </header>
        <div class="sensor-grid" :class="{ sparse: sortedSensors.length < 4 }">
          <div v-if="!sortedSensors.length" class="sensor-empty"><i></i>AWAITING TELEMETRY / 等待测点接入</div>
          <button
            v-for="s in sortedSensors"
            :key="s.sensor_id"
            class="sensor-cell"
            :class="getLevel(s)"
            type="button"
            :title="`${s.name} · ${s.value.toFixed(2)} ${unitName(s.type)} · ${s.connection_state === 'online' ? '在线' : '离线'} · ${getLevelText(getLevel(s))}`"
            @click="focusSensor(s.sensor_id)"
          >
            <span class="sensor-dot"></span>
            <span class="sensor-id">{{ s.sensor_id }}</span>
            <span class="sensor-name">{{ s.name }}</span>
            <span class="sensor-value">{{ s.value.toFixed(2) }}<em>{{ unitName(s.type) }}</em></span>
          </button>
        </div>
      </section>

      <section class="block chart-block">
        <header class="block-head">
          <span class="code">02</span>
          <h2>MEASUREMENT TREND</h2>
          <span class="note">实时趋势</span>
        </header>
        <div class="chart" ref="chartRef"></div>
        <div v-if="!sensors.length" class="chart-empty">AWAITING TREND DATA / 等待趋势数据</div>
        <div class="chart-key">
          <span class="s1"><i></i>{{ roleLabel('primary_strain', '跨中应变') }}</span>
          <span class="s3"><i></i>{{ roleLabel('tower_displacement', '塔顶位移') }}</span>
          <span class="s4"><i></i>{{ roleLabel('cable_acceleration', '拉索振动') }}</span>
        </div>
      </section>

      <section class="block alert-block">
        <header class="block-head">
          <span class="code">03</span>
          <h2>ALERT LOG</h2>
          <span class="alert-counts">
            <span><i class="r"></i>{{ redCount }}</span>
            <span><i class="o"></i>{{ orangeCount }}</span>
            <span><i class="y"></i>{{ yellowCount }}</span>
          </span>
        </header>
        <div class="alert-list" v-if="alerts.length">
          <article v-for="a in alerts.slice(0, 3)" :key="a.id" class="alert-row" :class="a.level">
            <span class="alert-level">{{ levelLabel(a.level) }}</span>
            <div class="alert-copy">
              <div class="alert-title">{{ a.sensor_name }}<span>{{ sourceLabel(a.source) }}</span></div>
              <div class="alert-msg">{{ a.message }}</div>
            </div>
            <time>{{ alertTime(a.timestamp) }}</time>
          </article>
        </div>
        <div class="no-alert" v-else><i></i>STRUCTURE NOMINAL · 系统运行正常，无告警</div>
      </section>

      <footer class="dossier-actions">
        <button class="action" type="button" @click="injectAnomaly('S01')">INJECT ANOMALY / S01</button>
        <button class="action accent" type="button" @click="exportReport">EXPORT REPORT</button>
      </footer>
    </aside>

    <footer class="dock">
      <div class="dock-id">
        <span>HISTORICAL REPLAY</span>
        <b>SHM–04 / {{ nowDate }}</b>
      </div>
      <div class="dock-transport">
        <button class="transport" type="button" :disabled="!historyRange.hasData" :aria-label="replayPlaying ? '暂停回放' : '播放回放'" @click="onToggleReplay">
          <svg v-if="!replayPlaying" viewBox="0 0 12 14" aria-hidden="true"><path d="M1 1l10 6-10 6z" /></svg>
          <svg v-else viewBox="0 0 12 14" aria-hidden="true"><path d="M1 1h3.2v12H1zM7.8 1H11v12H7.8z" /></svg>
        </button>
        <div class="timeline">
          <div class="timeline-meta">
            <span>{{ historyRange.hasData ? 'RECORDED WINDOW' : 'NO ARCHIVE LINK' }}</span>
            <b>{{ replayTimeText }}</b>
          </div>
          <div class="timeline-track">
            <span class="timeline-fill" :style="{ width: replayProgress + '%' }"></span>
            <span class="timeline-knob" :style="{ left: replayProgress + '%' }"></span>
            <input
              type="range"
              :min="historyRange.start"
              :max="historyRange.end"
              :step="10"
              :disabled="!historyRange.hasData"
              v-model.number="replayCurrentTs"
              aria-label="历史回放时间轴"
              @input="onReplaySeek"
            />
          </div>
        </div>
        <button class="transport text" type="button" :disabled="!historyRange.hasData" aria-label="重置回放" @click="onResetReplay">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5a5.5 5.5 0 1 1-5.2 7.3l1.4-.5A4 4 0 1 0 8 4v2.2L4.8 3.1 8 .4z" /></svg>
        </button>
        <select v-model.number="replaySpeed" class="speed" aria-label="回放速度">
          <option :value="1">1×</option>
          <option :value="2">2×</option>
          <option :value="4">4×</option>
          <option :value="8">8×</option>
          <option :value="16">16×</option>
        </select>
        <button v-if="replayMode" class="exit" type="button" @click="onExitReplay">EXIT REPLAY</button>
      </div>
      <div class="dock-actions">
        <span class="frame-time">LAST FRAME <b>{{ lastUpdate || '—' }}</b></span>
        <span class="view-hint">ROTATE · ZOOM · PAN</span>
      </div>
    </footer>

    <ModelImportDialog v-model="modelDialogVisible" @activated="onModelActivated" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'

import { apiFetch, apiUrl } from './api'
import PressureCloud from './components/PressureCloud.vue'
import ModelImportDialog from './components/ModelImportDialog.vue'
import { profileDisplayString } from './scene/bridgeSceneProfile'
import {
  BridgeSceneRuntime,
  type BridgeScenePick
} from './scene/bridgeSceneRuntime'
import {
  applyMeasurementRoles,
  createMeasurementChart,
  updateMeasurementChart,
  type MeasurementChart
} from './monitoring/measurementChart'
import { MeasurementTimeline } from './monitoring/measurementTimeline'
import { useMonitoringSession } from './composables/useMonitoringSession'
import type {
  ActiveBridgeModel,
  BridgeSceneProfile,
  PressureField,
  SensorReading as Sensor
} from './types/live'

const session = useMonitoringSession()
const {
  connected,
  sensors,
  alerts,
  stats,
  pressureField,
  lastUpdate: sessionLastUpdate,
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
  replayProgress
} = session
const totalReadings = computed(() => stats.value?.total_readings ?? 0)
const onlineSensorCount = computed(() => stats.value?.online_sensor_count ?? 0)
const nowDate = ref('')
const nowClock = ref('')
const uptimeTick = ref(Date.now())
const lastUpdate = computed(() => (
  sessionLastUpdate.value
    ? new Date(sessionLastUpdate.value).toLocaleTimeString()
    : ''
))
const startTime = ref(Date.now())
const viewerRef = ref<HTMLDivElement>()
const chartRef = ref<HTMLDivElement>()
const pressureOverlayEnabled = ref(true)
const modelDialogVisible = ref(false)
const activeModelLabel = ref('内置模型')
const activeModelIsBundled = ref(true)
const activeProfile = ref<BridgeSceneProfile | null>(null)
const sceneError = ref('')

let chart: MeasurementChart | null = null
const measurementTimeline = new MeasurementTimeline(60)

// 点击弹窗
const popup = ref({
  show: false,
  x: 0, y: 0,
  title: '',
  data: {} as Record<string, string | number>
})

let timer: number | null = null
let sceneRuntime: BridgeSceneRuntime | null = null

const replayMode = computed(() => mode.value === 'replay')

const uptime = computed(() => Math.max(0, Math.floor((uptimeTick.value - startTime.value) / 1000)))
const uptimeText = computed(() => {
  const total = uptime.value
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  return [hours, minutes, seconds].map(pad2).join(':')
})
const alertCount = computed(() => alerts.value.length)
const redCount = computed(() => alerts.value.filter(a => a.level === 'red').length)
const orangeCount = computed(() => alerts.value.filter(a => a.level === 'orange').length)
const yellowCount = computed(() => alerts.value.filter(a => a.level === 'yellow').length)
const sortedSensors = computed(() => [...sensors.value].sort((a, b) => a.sensor_id.localeCompare(b.sensor_id)))
const systemLevel = computed<'normal' | 'yellow' | 'orange' | 'red'>(() => {
  if (redCount.value > 0) return 'red'
  if (orangeCount.value > 0) return 'orange'
  if (yellowCount.value > 0) return 'yellow'
  return 'normal'
})
const systemStateZh = computed(() => ({
  normal: '结构状态正常',
  yellow: '存在注意级测点',
  orange: '存在警告级告警',
  red: '存在危险级告警'
})[systemLevel.value])
const systemStateEn = computed(() => ({
  normal: 'STRUCTURE NOMINAL',
  yellow: 'CAUTION REGISTERED',
  orange: 'ATTENTION REQUIRED',
  red: 'STRUCTURAL ALERT'
})[systemLevel.value])

function compactModelLabel(value: string, limit = 24) {
  const text = value.trim() || '内置模型'
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
}

const brandTitle = computed(() => {
  const displayName = profileDisplayString(activeProfile.value, 'name_en')
  if (displayName) return compactModelLabel(displayName, 22).toUpperCase()
  if (activeModelIsBundled.value) return 'HUIHE BRIDGE'
  return compactModelLabel(activeModelLabel.value, 22).toUpperCase()
})
const stageDisplayName = computed(() => {
  const displayName = profileDisplayString(activeProfile.value, 'name_zh')
  if (displayName) return compactModelLabel(displayName, 18)
  return activeModelIsBundled.value ? '浍河大桥' : compactModelLabel(activeModelLabel.value, 18)
})
const stageEnglishName = computed(() => {
  const displayName = profileDisplayString(activeProfile.value, 'name_en')
  if (displayName) return compactModelLabel(displayName, 24).toUpperCase()
  return activeModelIsBundled.value ? 'HUIHE BRIDGE' : 'IMPORTED MODEL'
})
const stageDescription = computed(() => {
  const display = activeProfile.value?.display || {}
  const modelKind = String(display.bridge_type || (activeModelIsBundled.value ? 'CABLE-STAYED' : 'IMPORTED GLTF'))
  const span = Number(display.span_m || 0)
  const spanText = Number.isFinite(span) && span > 0 ? ` · ${Math.round(span)} M` : ''
  const nodeCount = sensors.value.length || Number(display.sensor_node_count || 0)
  return `${modelKind}${spanText} · ${nodeCount} SENSOR NODES`
})

function roleLabel(role: string, fallback: string) {
  const definition = measurementTimeline
    .seriesDefinitions()
    .find((item) => item.key === role)
  return definition?.label || `${fallback} UNAVAILABLE`
}

watch([activeModelLabel, activeModelIsBundled], () => {
  document.title = activeModelIsBundled.value
    ? '桥梁结构健康监测'
    : `${compactModelLabel(activeModelLabel.value, 24)} · 结构健康监测`
}, { immediate: true })

watch(pressureOverlayEnabled, (visible) => {
  sceneRuntime?.setPressureOverlayEnabled(visible)
})

watch(frameVersion, () => {
  sceneRuntime?.setSensors(sensors.value)
  sceneRuntime?.setPressureField(pressureField.value)
  if (mode.value === 'live') appendLiveTrend()
  else appendReplayTrend()
})

function resetTrend() {
  measurementTimeline.reset()
  updateTrendChart()
}

function onToggleReplay() {
  if (mode.value === 'live') resetTrend()
  session.toggleReplay()
}

function onResetReplay() {
  resetTrend()
  void session.resetReplay()
}

function onExitReplay() {
  resetTrend()
  session.exitReplay()
}

function onReplaySeek() {
  void session.seekReplay()
}

function tick() {
  const date = new Date()
  nowDate.value = date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).replace(/\//g, '.')
  nowClock.value = date.toLocaleTimeString('zh-CN', { hour12: false })
  uptimeTick.value = Date.now()
}

async function injectAnomaly(id: string) {
  try {
    await apiFetch(`/api/analysis/inject-anomaly?sensor_id=${id}`, { method: 'POST' })
  } catch {}
}

function resetView() {
  sceneRuntime?.resetView()
}

function focusSensor(id: string) {
  sceneRuntime?.focusSensor(id)
}

// ====== 工具函数 ======
function typeName(t: string) {
  return { strain: '应变', displacement: '位移', acceleration: '加速度', temperature: '温度' }[t] || t
}
function unitName(t: string) {
  return { strain: 'με', displacement: 'mm', acceleration: 'm/s²', temperature: '°C' }[t] || ''
}

function pad2(value: number) {
  return String(value).padStart(2, '0')
}

function levelLabel(level: string) {
  return ({ red: 'ALERT', orange: 'WARN', yellow: 'CAUT', normal: 'OK' } as Record<string, string>)[level] || level.toUpperCase()
}

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    rule: 'RULE',
    ai_stalwart: 'STALWART',
    ai_gan_ae: 'GAN·AE',
    ai_isolation_forest: 'ISOLATION FOREST',
    ai_dual_confirm: 'DUAL CONFIRM',
    ai_feature_arbitration: 'ARBITRATION'
  }
  return labels[source] || source.toUpperCase()
}

function alertTime(timestamp: number | null) {
  if (!timestamp) return '--:--'
  return new Date(timestamp * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

function getLevel(s: Sensor): string {
  if (s.physical_state === 'red') return 'danger'
  if (s.physical_state === 'orange') return 'warning'
  if (s.physical_state === 'yellow') return 'caution'
  if (s.physical_state === 'normal') return 'normal'
  return 'unknown'
}

// ====== ECharts 图表 ======
function initChart() {
  if (!chartRef.value || chartRef.value.clientWidth === 0 || chartRef.value.clientHeight === 0) return
  if (chart && !chart.isDisposed()) {
    chart.resize()
    return
  }
  chart = createMeasurementChart(
    chartRef.value,
    measurementTimeline.seriesDefinitions()
  )
  applyChartRoles()
  updateTrendChart()
}

function applyChartRoles() {
  if (!chart || chart.isDisposed()) return
  applyMeasurementRoles(chart, measurementTimeline.seriesDefinitions())
}

function updateTrendChart() {
  if (!chart || chart.isDisposed()) return
  updateMeasurementChart(chart, measurementTimeline.snapshot())
}

function appendLiveTrend() {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  measurementTimeline.appendSensors(sensors.value, time)
  updateTrendChart()
}

function appendReplayTrend() {
  const time = new Date(replayCurrentTs.value * 1000).toLocaleTimeString('zh-CN', {
    hour12: false
  })
  measurementTimeline.appendSnapshot(replaySnapshot.value, time)
  updateTrendChart()
}

function configureTrendForProfile(profile: BridgeSceneProfile | null) {
  const roles = profile?.measurement_roles || {}
  measurementTimeline.configure(
    profile ? `${profile.profile_id}:${profile.revision}` : '',
    {
      primary_strain: String(roles.primary_strain || ''),
      tower_displacement: String(roles.tower_displacement || ''),
      cable_acceleration: String(roles.cable_acceleration || '')
    }
  )
  applyChartRoles()
  updateTrendChart()
}
function resizeChart() {
  if (chart && !chart.isDisposed()) chart.resize()
  else initChart()
}

function mountScene() {
  const container = viewerRef.value
  if (!container) return
  sceneRuntime = new BridgeSceneRuntime({
    container,
    onPick: handleScenePick,
    onViewportResize: resizeChart
  })
  sceneRuntime.start()
  sceneRuntime.setPressureOverlayEnabled(pressureOverlayEnabled.value)
  void loadActiveBridgeModel()
}

async function loadActiveBridgeModel() {
  let payload: ActiveBridgeModel
  let profile: BridgeSceneProfile
  try {
    const response = await apiFetch('/api/models/active')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    payload = (await response.json()) as ActiveBridgeModel
    const profileResponse = await apiFetch(payload.profile_url)
    if (!profileResponse.ok) {
      throw new Error(`Scene profile HTTP ${profileResponse.status}`)
    }
    profile = (await profileResponse.json()) as BridgeSceneProfile
    activeModelLabel.value = payload.active?.name || '内置模型'
    activeModelIsBundled.value = payload.active === null
    activeProfile.value = profile
    sceneError.value = ''
    configureTrendForProfile(profile)
    applyChartRoles()
  } catch (error) {
    console.error('读取激活模型或 Scene Profile 失败', error)
    sceneError.value = error instanceof Error ? error.message : '无法读取 Scene Profile'
    activeProfile.value = null
    return
  }

  if (!sceneRuntime) return
  try {
    await sceneRuntime.loadModel({
      fileUrl: apiUrl(payload.file_url),
      label: activeModelLabel.value,
      addDefaultCables: payload.active === null,
      profile
    })
  } catch (error) {
    console.error('桥梁模型加载失败', error)
    sceneError.value = error instanceof Error ? error.message : '模型加载失败'
    return
  }
  sceneRuntime.setSensors(sensors.value)
  sceneRuntime.setPressureField(pressureField.value)
  popup.value.show = false
}

async function onModelActivated() {
  modelDialogVisible.value = false
  await loadActiveBridgeModel()
}

function handleScenePick(pick: BridgeScenePick) {
  if (pick.kind === 'background') {
    popup.value.show = false
    return
  }
  const viewerEl = viewerRef.value
  const parentEl = viewerEl?.parentElement
  if (!parentEl) return
  const parentRect = parentEl.getBoundingClientRect()
  const popupX = pick.clientX - parentRect.left + 10
  const popupY = pick.clientY - parentRect.top - 10

  if (pick.kind === 'sensor') {
    const sensor = sensors.value.find((item) => item.sensor_id === pick.sensorId)
    if (!sensor) return
    popup.value = {
      show: true,
      x: popupX,
      y: popupY,
      title: `${sensor.name} / ${sensor.sensor_id}`,
      data: {
        '传感器类型': typeName(sensor.type),
        '当前读数': `${sensor.value.toFixed(2)} ${unitName(sensor.type)}`,
        '健康状态': getLevelText(getLevel(sensor)),
        '更新时间': new Date(sensor.timestamp * 1000).toLocaleTimeString('zh-CN')
      }
    }
    return
  }

  let title = ''
  let partType = ''
  let relatedSensors = ''
  if (pick.partNameZh) {
    title = pick.partNameZh
  } else {
    const names: Record<string, string> = {
      tower_left: '左索塔',
      tower_right: '右索塔',
      deck: '主梁 / 桥面'
    }
    title = names[pick.partName] || pick.partName
  }

  if (activeProfile.value?.source !== 'bundled') {
    partType = '导入模型构件'
    relatedSensors = '由 Bridge Scene Profile 提供'
  } else if (pick.partName.startsWith('tower')) {
    partType = 'H型钢筋混凝土索塔，高50m'
    relatedSensors = pick.partNameZh?.includes('右')
      ? 'S03（塔顶位移）、S06（塔底应变）'
      : 'S04（拉索振动）'
  } else if (pick.partName === 'deck') {
    partType = '单箱单室混凝土箱梁，梁高2.5m，宽14m'
    relatedSensors = 'S01（跨中应变）、S02（1/4跨应变）、S05（跨中挠度）、S08（温度）'
  } else if (pick.partName === 'pier') {
    partType = '钢筋混凝土桥墩，直径2.5m'
    relatedSensors = '无直接监测传感器'
  } else if (pick.partName === 'cap') {
    partType = '钢筋混凝土承台，12m×12m×3.5m'
    relatedSensors = '无直接监测传感器'
  } else if (pick.partName === 'cable') {
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
    title,
    data: {
      '构件类型': partType,
      '健康状态': 'NORMAL / 正常',
      '关联传感器': relatedSensors
    }
  }
}
function getLevelText(level: string): string {
  return { normal: 'NORMAL / 正常', caution: 'CAUTION / 注意', warning: 'WARNING / 警告', danger: 'ALERT / 危险' }[level] || 'UNKNOWN / 未知'
}

// ====== 导出报告 ======
function exportReport() {
  window.open(apiUrl('/api/analysis/report?hours=24'), '_blank')
}

// ====== 生命周期 ======
onMounted(async () => {
  await nextTick()
  mountScene()
  initChart()
  tick()
  timer = window.setInterval(tick, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  sceneRuntime?.dispose()
  sceneRuntime = null
  if (chart) chart.dispose()
})
</script>

<style>
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: 300; font-display: swap; src: url('./assets/fonts/Montserrat-Light.woff2') format('woff2'); }
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: 400; font-display: swap; src: url('./assets/fonts/Montserrat-Regular.woff2') format('woff2'); }
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: 500; font-display: swap; src: url('./assets/fonts/Montserrat-Medium.woff2') format('woff2'); }
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: 600; font-display: swap; src: url('./assets/fonts/Montserrat-SemiBold.woff2') format('woff2'); }
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: 700; font-display: swap; src: url('./assets/fonts/Montserrat-Bold.woff2') format('woff2'); }
@font-face { font-family: 'Montserrat'; font-style: normal; font-weight: 800; font-display: swap; src: url('./assets/fonts/Montserrat-ExtraBold.woff2') format('woff2'); }
@font-face { font-family: 'JetBrains Mono'; font-style: normal; font-weight: 400; font-display: swap; src: url('./assets/fonts/JetBrainsMono-Regular.woff2') format('woff2'); }
@font-face { font-family: 'JetBrains Mono'; font-style: normal; font-weight: 500; font-display: swap; src: url('./assets/fonts/JetBrainsMono-Medium.woff2') format('woff2'); }
@font-face { font-family: 'JetBrains Mono'; font-style: normal; font-weight: 600; font-display: swap; src: url('./assets/fonts/JetBrainsMono-SemiBold.woff2') format('woff2'); }

:root {
  --paper: #e7e5e1;
  --paper-hi: #f4f3ef;
  --paper-lo: #d8d5ce;
  --ink: #111214;
  --ink-soft: #242427;
  --mute: #77746d;
  --faint: #b7b3ab;
  --line: rgba(17, 18, 20, 0.18);
  --line-soft: rgba(17, 18, 20, 0.1);
  --lime: #b9e432;
  --orange: #ff6a00;
  --amber: #d9a300;
  --red: #e23b12;
  --accent: #b9e432;
  --signal: #111214;
  --signal-text: #77746d;
  --display: 'Montserrat', 'MiSans', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --mono: 'JetBrains Mono', 'Cascadia Mono', 'Consolas', monospace;
  --cjk: 'MiSans', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
}

* { box-sizing: border-box; }
html, body, #app { width: 100%; height: 100%; margin: 0; padding: 0; }
body {
  background: var(--paper);
  color: var(--ink);
  font-family: var(--display);
  -webkit-font-smoothing: antialiased;
  overflow: hidden;
}
button, input, select { font: inherit; color: inherit; }
button { -webkit-tap-highlight-color: transparent; }
::selection { background: var(--lime); color: var(--ink); }

.app {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 448px;
  grid-template-rows: 88px minmax(0, 1fr) 80px;
  overflow: hidden;
  background: var(--paper);
}
.app.level-yellow { --accent: var(--amber); --signal: var(--amber); --signal-text: #8a6500; }
.app.level-orange { --accent: var(--orange); --signal: var(--orange); --signal-text: #c24a00; }
.app.level-red { --accent: var(--orange); --signal: var(--red); --signal-text: #b12908; }

/* ---------- topbar ---------- */
.topbar {
  grid-column: 1 / -1;
  grid-row: 1;
  min-width: 0;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 24px;
  padding: 0 24px;
  background: var(--paper-hi);
  border-bottom: 1px solid var(--ink);
  z-index: 30;
}
.brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
.brand-mark {
  position: relative;
  width: 44px;
  height: 44px;
  flex: none;
  display: grid;
  place-items: center;
  background: var(--ink);
  color: var(--paper);
}
.brand-mark::after {
  content: '';
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 5px;
  height: 5px;
  background: var(--accent);
}
.brand-mark svg { width: 30px; height: 30px; fill: none; stroke: currentColor; stroke-width: 1.5; }
.brand-lockup { display: flex; flex-direction: column; justify-content: center; line-height: 1; padding: 12px 0; white-space: nowrap; }
.brand-l1 { font-family: var(--display); font-size: 22px; font-weight: 800; letter-spacing: 0.015em; }
.brand-l2 { margin-top: 5px; color: var(--mute); font-family: var(--mono); font-size: 7.5px; font-weight: 500; letter-spacing: 1.6px; }
.brand-l3 { display: flex; align-items: baseline; gap: 5px; margin-top: 4px; font-size: 16px; letter-spacing: 0.04em; }
.brand-l3 span { font-weight: 300; }
.brand-l3 b { font-weight: 800; }

.topbar-mid {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-left: auto;
  color: var(--mute);
  font-family: var(--mono);
  font-size: 7.5px;
  letter-spacing: 1.1px;
  white-space: nowrap;
}
.topbar-mid i { width: 38px; height: 1px; background: var(--faint); }

.topbar-actions { display: flex; align-items: center; gap: 18px; min-width: 0; }
.conn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--mute);
  font-family: var(--mono);
  font-size: 7.5px;
  letter-spacing: 0.8px;
  white-space: nowrap;
}
.conn i { width: 6px; height: 6px; flex: none; background: var(--faint); }
.conn.on i { background: var(--lime); box-shadow: 0 0 0 3px rgba(185, 228, 50, 0.22); }
.conn.replay i { background: var(--orange); box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.16); }
.model-ref {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--mute);
  font-family: var(--mono);
  font-size: 7px;
  letter-spacing: 0.7px;
}
.import-btn {
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0 11px;
  border: 1px solid var(--ink);
  background: transparent;
  cursor: pointer;
  font-family: var(--mono);
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 1px;
  white-space: nowrap;
  transition: background 140ms, color 140ms;
}
.import-btn svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 1.2; }
.import-btn:hover { background: var(--ink); color: var(--paper); }
.clock { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; font-family: var(--mono); }
.clock span { color: var(--mute); font-size: 7.5px; letter-spacing: 0.8px; }
.clock b {
  color: var(--ink);
  font-family: var(--display);
  font-size: 29px;
  font-weight: 300;
  line-height: 0.9;
  letter-spacing: -0.045em;
}

/* ---------- stage ---------- */
.stage {
  grid-column: 1;
  grid-row: 2;
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--paper);
}
.viewer { position: absolute; inset: 0; }
.viewer canvas { display: block; width: 100%; height: 100%; }
.scene-error {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 9;
  width: min(420px, calc(100% - 48px));
  transform: translate(-50%, -50%);
  padding: 18px 20px;
  border: 1px solid var(--red);
  background: rgba(244, 243, 239, 0.96);
  box-shadow: 8px 8px 0 rgba(226, 59, 18, 0.14);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.scene-error span { color: var(--red); font-family: var(--mono); font-size: 7px; letter-spacing: 1px; }
.scene-error strong { color: var(--ink); font-family: var(--cjk); font-size: 12px; font-weight: 500; line-height: 1.5; }
.stage-grid {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  opacity: 0.5;
  background-image:
    linear-gradient(90deg, rgba(17, 18, 20, 0.06) 1px, transparent 1px),
    linear-gradient(180deg, rgba(17, 18, 20, 0.06) 1px, transparent 1px);
  background-size: 76px 76px;
  -webkit-mask-image: radial-gradient(ellipse at 54% 48%, transparent 0%, transparent 42%, #000 100%);
  mask-image: radial-gradient(ellipse at 54% 48%, transparent 0%, transparent 42%, #000 100%);
}
.stage::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background:
    radial-gradient(ellipse at 55% 44%, transparent 34%, rgba(17, 18, 20, 0.055) 100%),
    linear-gradient(180deg, rgba(17, 18, 20, 0.025), transparent 18%, transparent 84%, rgba(17, 18, 20, 0.03));
}
.corner { position: absolute; width: 17px; height: 17px; z-index: 3; border: 0 solid var(--ink); opacity: 0.45; pointer-events: none; }
.corner.tl { left: 10px; top: 10px; border-top-width: 1px; border-left-width: 1px; }
.corner.tr { right: 10px; top: 10px; border-top-width: 1px; border-right-width: 1px; }
.corner.bl { left: 10px; bottom: 10px; border-bottom-width: 1px; border-left-width: 1px; }
.corner.br { right: 10px; bottom: 10px; border-bottom-width: 1px; border-right-width: 1px; }

.rail {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 5;
  width: 42px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 22px 0 18px;
  border-right: 1px solid var(--line);
  pointer-events: none;
}
.rail-index { font-family: var(--mono); font-size: 10px; font-weight: 600; letter-spacing: 0.05em; }
.rail-nodes { display: flex; flex-direction: column; gap: 6px; }
.rail-nodes span { width: 5px; height: 5px; background: var(--ink); opacity: 0.3; }
.rail-nodes span.caution { background: var(--amber); opacity: 1; }
.rail-nodes span.warning { background: var(--orange); opacity: 1; }
.rail-nodes span.danger { background: var(--red); opacity: 1; }
.rail-nodes span.unknown { background: var(--faint); opacity: 0.75; }
.rail-rule { flex: 1; width: 1px; background: var(--line); }
.rail-caption {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  color: var(--mute);
  font-family: var(--mono);
  font-size: 6.5px;
  letter-spacing: 1.8px;
  white-space: nowrap;
}

.stage-title { position: absolute; left: 76px; top: 26px; z-index: 5; pointer-events: none; }
.stage-kicker { color: var(--mute); font-family: var(--mono); font-size: 7px; letter-spacing: 1.4px; }
.stage-title h1 { margin: 8px 0 5px; font-family: var(--cjk); font-size: 32px; font-weight: 600; line-height: 1; letter-spacing: 0.08em; }
.stage-title h1 span { margin-left: 12px; color: var(--mute); font-family: var(--display); font-size: 10px; font-weight: 700; letter-spacing: 2.2px; vertical-align: middle; }
.stage-sub { color: var(--mute); font-family: var(--mono); font-size: 7.5px; letter-spacing: 1.2px; }
.stage-readout { display: flex; gap: 14px; margin-top: 13px; }
.stage-readout span { padding-top: 4px; border-top: 1px solid var(--ink); font-family: var(--mono); font-size: 7px; letter-spacing: 0.6px; }

.stage-tools { position: absolute; right: 22px; top: 22px; z-index: 7; display: flex; align-items: center; gap: 6px; }
.source-chip { margin-right: 4px; padding-bottom: 3px; border-bottom: 1px solid var(--faint); color: var(--mute); font-family: var(--mono); font-size: 7px; letter-spacing: 0.7px; }
.tool {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  border: 1px solid rgba(17, 18, 20, 0.42);
  background: rgba(244, 243, 239, 0.6);
  -webkit-backdrop-filter: blur(5px);
  backdrop-filter: blur(5px);
  cursor: pointer;
  font-family: var(--mono);
  font-size: 7px;
  letter-spacing: 0.7px;
  transition: background 140ms, color 140ms, border-color 140ms;
}
.tool i { width: 5px; height: 5px; background: currentColor; opacity: 0.35; }
.tool:hover { border-color: var(--ink); background: var(--paper-hi); }
.tool.active { border-color: var(--ink); background: var(--ink); color: var(--paper); }
.tool.active i { background: var(--accent); opacity: 1; }
.view-hint { position: absolute; right: 23px; top: 58px; z-index: 5; color: var(--faint); font-family: var(--mono); font-size: 6.5px; letter-spacing: 0.7px; pointer-events: none; }

.info-popup {
  position: absolute;
  z-index: 20;
  width: 250px;
  max-width: calc(100% - 40px);
  background: var(--paper-hi);
  border: 1px solid var(--ink);
  box-shadow: 8px 8px 0 rgba(17, 18, 20, 0.14);
}
.popup-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  background: var(--ink);
  color: var(--paper);
  font-family: var(--mono);
  font-size: 7.5px;
  letter-spacing: 0.6px;
}
.popup-close { border: 0; background: none; color: var(--paper); cursor: pointer; font-size: 15px; line-height: 1; padding: 0 2px; }
.popup-body { padding: 7px 9px 9px; }
.popup-row { display: flex; justify-content: space-between; gap: 14px; padding: 5px 0; border-bottom: 1px dotted var(--line); font-size: 8px; }
.popup-row:last-child { border-bottom: 0; }
.pk { color: var(--mute); font-family: var(--cjk); }
.pv { font-family: var(--mono); font-weight: 500; text-align: right; }

.stage-pressure { position: absolute; left: 76px; bottom: 24px; z-index: 8; width: 380px; }
.legend {
  position: absolute;
  right: 24px;
  bottom: 22px;
  z-index: 7;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 9px;
  border: 1px solid var(--line);
  background: rgba(244, 243, 239, 0.66);
  -webkit-backdrop-filter: blur(5px);
  backdrop-filter: blur(5px);
  font-family: var(--mono);
  font-size: 6.5px;
  letter-spacing: 0.5px;
}
.legend span { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.legend i { width: 5px; height: 5px; background: var(--ink); }
.legend i.y { background: var(--amber); }
.legend i.o { background: var(--orange); }
.legend i.r { background: var(--red); }
/* ---------- dossier ---------- */
.dossier {
  grid-column: 2;
  grid-row: 2;
  position: relative;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--paper-hi);
  border-left: 1px solid var(--ink);
}
.dossier::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  z-index: 2;
  background: var(--accent);
}
.dossier-tags {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px 0 19px;
  font-family: var(--mono);
  font-size: 6.5px;
  letter-spacing: 0.9px;
}
.tag-solid { padding: 2px 6px; background: var(--ink); color: var(--paper); }
.tag-rule { padding-bottom: 2px; border-bottom: 1px solid var(--faint); color: var(--mute); }

.dossier-state {
  flex: none;
  padding: 10px 18px 10px 19px;
  border-bottom: 1px solid var(--line);
}
.micro { color: var(--mute); font-family: var(--mono); font-size: 6.5px; letter-spacing: 1px; }
.state-value { display: flex; align-items: center; gap: 9px; margin-top: 5px; }
.state-dot { width: 8px; height: 8px; flex: none; background: var(--signal); box-shadow: 0 0 0 4px color-mix(in srgb, var(--signal) 14%, transparent); }
.state-value strong { font-family: var(--cjk); font-size: 18px; font-weight: 600; letter-spacing: 0.05em; }
.state-en { display: block; margin-top: 4px; color: var(--signal-text); font-family: var(--mono); font-size: 7.5px; letter-spacing: 1.15px; }

.stat-grid {
  flex: none;
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--line);
}
.stat { padding: 7px 18px 8px 19px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.stat:nth-child(2n) { border-right: 0; }
.stat:nth-child(n + 3) { border-bottom: 0; }
.stat-label { display: block; color: var(--mute); font-family: var(--mono); font-size: 6.4px; letter-spacing: 0.85px; }
.stat-value { display: block; margin-top: 3px; font-family: var(--mono); font-size: 24px; font-weight: 500; line-height: 1; letter-spacing: -0.035em; }
.stat-value small { margin-left: 2px; color: var(--faint); font-size: 9px; font-weight: 400; letter-spacing: 0; }
.stat-zh { display: block; margin-top: 4px; color: var(--mute); font-family: var(--cjk); font-size: 8.5px; }
.alert-number { color: var(--ink); }
.level-orange .alert-number, .level-red .alert-number { color: var(--signal); }

.block { display: flex; flex-direction: column; min-height: 0; border-bottom: 1px solid var(--line); }
.block-head { flex: none; display: flex; align-items: center; gap: 7px; padding: 6px 18px 5px 19px; }
.block-head .code { padding: 1px 4px; background: var(--ink); color: var(--paper); font-family: var(--mono); font-size: 6px; line-height: 1.5; }
.block-head h2 { margin: 0; font-family: var(--display); font-size: 8px; font-weight: 700; letter-spacing: 1.05px; }
.block-head .note { margin-left: auto; color: var(--mute); font-family: var(--cjk); font-size: 8px; }

.sensors-block { flex: 1.25 1 0; }
.sensor-grid { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: minmax(39px, 1fr); align-content: stretch; overflow: auto; }
.sensor-grid.sparse { grid-auto-rows: minmax(39px, auto); align-content: start; }
.sensor-empty { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; padding: 16px 18px 16px 19px; color: var(--mute); font-family: var(--mono); font-size: 7px; letter-spacing: 0.5px; }
.sensor-empty i { width: 6px; height: 6px; background: var(--faint); }
.sensor-cell {
  position: relative;
  min-height: 39px;
  display: grid;
  grid-template-columns: 5px 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px;
  padding: 0 10px 0 19px;
  border: 0;
  border-top: 1px solid var(--line-soft);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 120ms;
}
.sensor-cell:nth-child(2n - 1) { border-right: 1px solid var(--line-soft); }
.sensor-cell:hover { background: var(--paper); }
.sensor-cell.danger { background: rgba(226, 59, 18, 0.06); }
.sensor-cell.danger:hover { background: rgba(226, 59, 18, 0.11); }
.sensor-dot { width: 5px; height: 5px; background: var(--ink); opacity: 0.35; }
.sensor-cell.caution .sensor-dot { background: var(--amber); opacity: 1; }
.sensor-cell.warning .sensor-dot { background: var(--orange); opacity: 1; }
.sensor-cell.danger .sensor-dot { background: var(--red); opacity: 1; }
.sensor-cell.unknown { color: var(--mute); }
.sensor-cell.unknown .sensor-dot { background: var(--faint); opacity: 0.75; }
.sensor-cell.unknown .sensor-value { color: var(--mute); }
.sensor-id { color: var(--mute); font-family: var(--mono); font-size: 8px; letter-spacing: 0.2px; }
.sensor-name { overflow: hidden; color: var(--ink); font-family: var(--cjk); font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }
.sensor-value { font-family: var(--mono); font-size: 11px; font-weight: 500; text-align: right; white-space: nowrap; }
.sensor-value em { margin-left: 1px; color: var(--mute); font-size: 7px; font-style: normal; font-weight: 400; }

.chart-block { position: relative; flex: 0 0 154px; }
.chart { flex: 1; min-height: 0; width: 100%; }
.chart-empty { position: absolute; left: 19px; right: 18px; top: 26px; bottom: 24px; display: flex; align-items: center; justify-content: center; color: var(--faint); font-family: var(--mono); font-size: 6.5px; letter-spacing: 0.6px; pointer-events: none; }
.chart-key { flex: none; display: flex; gap: 12px; padding: 0 18px 7px 19px; color: var(--mute); font-family: var(--cjk); font-size: 7.5px; }
.chart-key span { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.chart-key i { display: inline-block; width: 11px; height: 2px; background: var(--ink); }
.chart-key .s3 i { background: var(--orange); }
.chart-key .s4 i { background: #8c9e2e; }

.alert-block { flex: 0.85 1 0; }
.alert-counts { display: flex; align-items: center; gap: 6px; margin-left: auto; font-family: var(--mono); font-size: 6.5px; }
.alert-counts span { display: inline-flex; align-items: center; gap: 2px; }
.alert-counts i { width: 4px; height: 4px; background: var(--red); }
.alert-counts i.o { background: var(--orange); }
.alert-counts i.y { background: var(--amber); }
.alert-list { flex: 1; min-height: 0; overflow: auto; }
.alert-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 42px;
  align-items: start;
  gap: 7px;
  padding: 5px 18px 5px 19px;
  border-top: 1px solid var(--line-soft);
}
.alert-level { margin-top: 1px; padding: 2px 0; background: var(--ink); color: var(--paper); font-family: var(--mono); font-size: 5.8px; letter-spacing: 0.2px; text-align: center; }
.alert-row.yellow .alert-level { background: var(--amber); color: var(--ink); }
.alert-row.orange .alert-level { background: var(--orange); color: var(--ink); }
.alert-row.red .alert-level { background: var(--red); color: var(--paper); }
.alert-copy { min-width: 0; }
.alert-title { font-family: var(--cjk); font-size: 9px; font-weight: 600; line-height: 1.25; }
.alert-title span { margin-left: 4px; color: var(--mute); font-family: var(--mono); font-size: 6px; font-weight: 400; letter-spacing: 0.2px; }
.alert-msg { display: -webkit-box; overflow: hidden; margin-top: 2px; color: var(--mute); font-family: var(--cjk); font-size: 8px; line-height: 1.35; -webkit-line-clamp: 1; -webkit-box-orient: vertical; }
.alert-row time { padding-top: 2px; color: var(--mute); font-family: var(--mono); font-size: 6.5px; text-align: right; white-space: nowrap; }
.no-alert { display: flex; align-items: center; gap: 8px; padding: 14px 18px 16px 19px; color: var(--mute); font-family: var(--mono); font-size: 7px; letter-spacing: 0.5px; }
.no-alert i { width: 6px; height: 6px; background: var(--lime); box-shadow: 0 0 0 3px rgba(185, 228, 50, 0.16); }

.dossier-actions { flex: none; display: grid; grid-template-columns: 1fr 1fr; height: 44px; }
.action { border: 0; border-right: 1px solid var(--line); background: transparent; cursor: pointer; font-family: var(--mono); font-size: 6.8px; letter-spacing: 0.65px; transition: background 140ms, color 140ms; }
.action:last-child { border-right: 0; }
.action:hover { background: var(--ink); color: var(--paper); }
.action.accent { background: var(--ink); color: var(--paper); }
.action.accent:hover { background: var(--accent); color: var(--ink); }

/* ---------- transport dock ---------- */
.dock {
  grid-column: 1 / -1;
  grid-row: 3;
  z-index: 30;
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr) 190px;
  align-items: center;
  gap: 20px;
  min-width: 0;
  padding: 0 24px;
  background: var(--ink);
  color: var(--paper);
  border-top: 1px solid var(--ink);
}
.dock-id { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.dock-id span { color: #8b8882; font-family: var(--mono); font-size: 6.5px; letter-spacing: 1.1px; }
.dock-id b { overflow: hidden; color: var(--paper); font-family: var(--mono); font-size: 9px; font-weight: 500; letter-spacing: 0.5px; white-space: nowrap; text-overflow: ellipsis; }
.dock-transport { display: flex; align-items: center; gap: 10px; min-width: 0; }
.transport {
  width: 30px;
  height: 30px;
  flex: none;
  display: grid;
  place-items: center;
  border: 1px solid #3d3d40;
  background: transparent;
  color: var(--paper);
  cursor: pointer;
  transition: border-color 120ms, color 120ms;
}
.transport svg { width: 11px; height: 12px; fill: currentColor; }
.transport.text svg { width: 12px; height: 12px; }
.transport:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.transport:disabled { opacity: 0.28; cursor: not-allowed; }
.timeline { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.timeline-meta { display: flex; justify-content: space-between; gap: 12px; color: #8b8882; font-family: var(--mono); font-size: 6px; letter-spacing: 0.8px; }
.timeline-meta b { overflow: hidden; color: var(--paper); font-size: 7.5px; font-weight: 500; letter-spacing: 0.35em; white-space: nowrap; text-overflow: ellipsis; }
.timeline-track { position: relative; height: 14px; }
.timeline-track::before { content: ''; position: absolute; left: 0; right: 0; top: 6px; height: 1px; background: #3f3f42; }
.timeline-fill { position: absolute; left: 0; top: 6px; height: 1px; background: var(--accent); }
.timeline-knob { position: absolute; top: 3px; width: 7px; height: 7px; margin-left: -3px; background: var(--accent); }
.timeline-track input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
.timeline-track input:disabled { cursor: not-allowed; }
.timeline-track:focus-within::before { background: #6b6b6e; }
.speed { height: 28px; padding: 0 6px; border: 1px solid #3d3d40; background: transparent; color: var(--paper); font-family: var(--mono); font-size: 7.5px; cursor: pointer; }
.speed option { background: var(--ink); color: var(--paper); }
.exit { height: 28px; padding: 0 8px; border: 1px solid var(--orange); background: transparent; color: var(--orange); font-family: var(--mono); font-size: 6.5px; letter-spacing: 0.5px; cursor: pointer; white-space: nowrap; }
.exit:hover { background: var(--orange); color: var(--ink); }
.dock-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; min-width: 0; }
.frame-time { color: #8b8882; font-family: var(--mono); font-size: 6px; letter-spacing: 0.6px; white-space: nowrap; }
.frame-time b { color: var(--paper); font-weight: 500; }
.dock-actions .view-hint { color: #5b5b5f; font-size: 6px; letter-spacing: 0.6px; right: auto; top: auto; position: static; }
/* ---------- scrollbars / focus / motion ---------- */
.sensor-grid, .alert-list { scrollbar-width: thin; scrollbar-color: var(--faint) transparent; }
.sensor-grid::-webkit-scrollbar, .alert-list::-webkit-scrollbar { width: 4px; height: 4px; }
.sensor-grid::-webkit-scrollbar-thumb, .alert-list::-webkit-scrollbar-thumb { background: var(--faint); }
.sensor-grid::-webkit-scrollbar-track, .alert-list::-webkit-scrollbar-track { background: transparent; }
button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}

/* ---------- responsive ---------- */
@media (max-width: 1480px) {
  .topbar-mid { display: none; }
}
@media (min-width: 1700px) {
  .brand-l1 { font-size: 22px; }
  .brand-l2 { font-size: 8px; }
  .brand-l3 { font-size: 16px; }
  .stage-title h1 { font-size: 38px; }
  .stage-title h1 span { font-size: 11px; }
  .stage-kicker, .stage-sub { font-size: 8px; }
  .stage-pressure { width: 420px; }
  .stat-value { font-size: 27px; }
  .stat-label { font-size: 6.8px; }
  .stat-zh { font-size: 9px; }
  .sensor-name { font-size: 9.5px; }
  .sensor-value { font-size: 12px; }
  .legend { font-size: 7px; }
}
@media (min-height: 1000px) {
  .chart-block { flex-basis: 196px; }
}
@media (max-width: 1340px) {
  .app { grid-template-columns: minmax(0, 1fr) 408px; }
  .clock b { font-size: 24px; }
  .model-ref { display: none; }
  .stage-pressure { width: 344px; }
  .legend { gap: 8px; }
}
@media (max-width: 1180px) {
  .app { grid-template-columns: minmax(0, 1fr) 380px; }
  .topbar { gap: 14px; padding: 0 18px; }
  .brand-l2 { display: none; }
  .brand-lockup { padding: 8px 0; }
  .brand-l1 { font-size: 18px; }
  .brand-l3 { font-size: 13px; margin-top: 3px; }
  .topbar-actions { gap: 12px; }
  .rail { display: none; }
  .stage-title { left: 24px; }
  .stage-pressure { left: 24px; width: 320px; }
  .stage-title h1 { font-size: 27px; }
  .stage-title h1 span { display: block; margin: 6px 0 0; }
  .stage-sub { margin-top: 6px; }
  .dossier-tags { padding-left: 15px; }
  .dossier-state, .stat, .sensor-cell, .block-head, .alert-row, .no-alert, .chart-key { padding-left: 15px; }
  .dock { grid-template-columns: 140px minmax(0, 1fr) 150px; gap: 14px; padding: 0 18px; }
  .source-chip { display: none; }
}
@media (max-width: 1100px) {
  .app {
    grid-template-columns: 1fr;
    grid-template-rows: 72px minmax(0, 1fr) 382px 66px;
  }
  .topbar { grid-row: 1; }
  .stage { grid-row: 2; }
  .dossier {
    grid-column: 1;
    grid-row: 3;
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto minmax(0, 1fr);
    border-left: 0;
    border-top: 1px solid var(--ink);
  }
  .dossier-tags { grid-column: 1 / -1; grid-row: 1; }
  .dossier-state { grid-column: 1; grid-row: 2; }
  .stat-grid { grid-column: 2; grid-row: 2; }
  .sensors-block { grid-column: 1; grid-row: 3; }
  .chart-block { display: none; }
  .alert-block { grid-column: 2; grid-row: 3; }
  .dossier-actions { grid-column: 1 / -1; grid-row: 4; }
  .stage-pressure, .legend, .view-hint, .topbar-mid, .model-ref { display: none; }
  .stage-title { left: 20px; top: 16px; }
  .stage-title h1 { font-size: 22px; }
  .stage-title h1 span { font-size: 8px; letter-spacing: 1.6px; }
  .stage-tools { right: 14px; top: 14px; }
  .tool { height: 26px; }
  .dock { grid-row: 4; grid-template-columns: minmax(0, 1fr); gap: 0; padding: 0 14px; }
  .dock-id, .dock-actions { display: none; }
  .speed { height: 26px; }
  .transport { width: 28px; height: 28px; }
}
@media (max-height: 860px) and (min-width: 1101px) {
  .app { grid-template-rows: 80px minmax(0, 1fr) 72px; }
  .clock b { font-size: 25px; }
  .dossier-tags { padding-top: 9px; }
  .dossier-state { padding: 7px 18px 7px 19px; }
  .state-value { margin-top: 3px; }
  .state-value strong { font-size: 16px; }
  .state-en { margin-top: 3px; }
  .stat { padding: 5px 18px 6px 19px; }
  .stat-value { font-size: 21px; }
  .stat-zh { margin-top: 2px; }
  .chart-block { flex-basis: 124px; }
  .chart-key { padding-bottom: 4px; }
  .dossier-actions { height: 40px; }
  .sensor-cell { min-height: 37px; }
  .alert-row { padding-top: 4px; padding-bottom: 4px; }
  .stage-pressure { width: 306px; }
  .stage-title { top: 20px; }
  .stage-title h1 { font-size: 28px; }
  .stage-sub { font-size: 7px; }
  .dock { grid-template-columns: 150px minmax(0, 1fr) 160px; }
  .alert-row:nth-child(n + 3) { display: none; }
}
@media (max-height: 760px) and (min-width: 1101px) {
  .app { grid-template-rows: 78px minmax(0, 1fr) 68px; }
  .stage-pressure { display: none; }
  .chart-block { flex-basis: 132px; }
  .dossier-tags { padding-top: 10px; }
  .dossier-state { padding-top: 7px; padding-bottom: 7px; }
}
</style>
