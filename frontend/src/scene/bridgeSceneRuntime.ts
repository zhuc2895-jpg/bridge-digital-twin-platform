import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import type {
  BridgeSceneProfile,
  PressureField,
  SensorReading
} from '../types/live'
import {
  applySceneProfile,
  pressureOverlayLayout,
  sceneCameraFit
} from './bridgeSceneProfile'

export type BridgeScenePick =
  | {
      kind: 'sensor'
      sensorId: string
      clientX: number
      clientY: number
    }
  | {
      kind: 'part'
      partName: string
      partNameZh: string
      clientX: number
      clientY: number
    }
  | {
      kind: 'background'
      clientX: number
      clientY: number
    }

export interface BridgeSceneRuntimeOptions {
  container: HTMLElement
  onPick?: (pick: BridgeScenePick) => void
  onViewportResize?: () => void
  onModelProgress?: (percent: number) => void
}

export interface BridgeSceneModelRequest {
  fileUrl: string
  label: string
  addDefaultCables: boolean
  profile: BridgeSceneProfile
}

const SENSOR_COLORS = {
  normal: new THREE.Color(0x111214),
  caution: new THREE.Color(0xd4a300),
  warning: new THREE.Color(0xff6a00),
  danger: new THREE.Color(0xe23b12),
  unknown: new THREE.Color(0x77746d)
}

const PRESSURE_STOPS: Array<[number, [number, number, number]]> = [
  [0, [12, 74, 110]],
  [0.25, [2, 132, 199]],
  [0.5, [34, 197, 94]],
  [0.75, [250, 204, 21]],
  [0.9, [249, 115, 22]],
  [1.25, [239, 68, 68]]
]

function sensorLevel(sensor: SensorReading): keyof typeof SENSOR_COLORS {
  if (sensor.physical_state === 'red') return 'danger'
  if (sensor.physical_state === 'orange') return 'warning'
  if (sensor.physical_state === 'yellow') return 'caution'
  if (sensor.physical_state === 'normal') return 'normal'
  return 'unknown'
}

function sensorColor(sensor: SensorReading): THREE.Color {
  return SENSOR_COLORS[sensorLevel(sensor)]
}

function pressureColor(value: number): [number, number, number] {
  const ratio = Math.max(0, Math.min(1.25, value))
  for (let index = 1; index < PRESSURE_STOPS.length; index += 1) {
    const [previousRatio, previousColor] = PRESSURE_STOPS[index - 1]
    const [currentRatio, currentColor] = PRESSURE_STOPS[index]
    if (ratio <= currentRatio) {
      const span = currentRatio - previousRatio || 1
      const t = (ratio - previousRatio) / span
      return [
        Math.round(previousColor[0] + (currentColor[0] - previousColor[0]) * t),
        Math.round(previousColor[1] + (currentColor[1] - previousColor[1]) * t),
        Math.round(previousColor[2] + (currentColor[2] - previousColor[2]) * t)
      ]
    }
  }
  return [239, 68, 68]
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child: any) => {
    child.geometry?.dispose?.()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    for (const material of materials) {
      material?.map?.dispose?.()
      material?.dispose?.()
    }
  })
}

export class BridgeSceneRuntime {
  private readonly container: HTMLElement
  private readonly options: BridgeSceneRuntimeOptions
  private scene!: THREE.Scene
  private camera!: THREE.PerspectiveCamera
  private renderer!: THREE.WebGLRenderer
  private controls!: OrbitControls
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private animationFrame = 0
  private resizeObserver: ResizeObserver | null = null
  private started = false

  private profile: BridgeSceneProfile | null = null
  private sensorsById = new Map<string, SensorReading>()
  private sensorMeshes: Record<string, THREE.Mesh> = {}
  private sensorRings: Record<string, THREE.Mesh> = {}
  private sensorGeometry: THREE.SphereGeometry | null = null
  private ringGeometry: THREE.RingGeometry | null = null
  private bridgeModel: THREE.Object3D | null = null
  private cableGroup: THREE.Group | null = null
  private loadSequence = 0

  private pressureField: PressureField | null = null
  private pressureOverlayEnabled = true
  private pressureOverlay: THREE.Mesh | null = null
  private pressureTexture: THREE.DataTexture | null = null
  private pressurePixels: Uint8Array<ArrayBuffer> | null = null
  private pressureDeckY = 20.2
  private pressurePlaneWidth = 240
  private pressurePlaneDepth = 20
  private pressurePlaneCenterX = 0
  private pressurePlaneCenterZ = 0

  constructor(options: BridgeSceneRuntimeOptions) {
    this.options = options
    this.container = options.container
  }

  start() {
    if (this.started) return
    this.started = true
    const width = Math.max(1, this.container.clientWidth)
    const height = Math.max(1, this.container.clientHeight)

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0xe7e5e1)
    this.scene.fog = new THREE.Fog(0xe7e5e1, 210, 430)

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000)
    this.camera.position.set(150, 80, 200)

    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setSize(width, height)
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.container.appendChild(this.renderer.domElement)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.target.set(0, 15, 0)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI / 2.1
    this.controls.minDistance = 30
    this.controls.maxDistance = 400
    this.controls.update()
    this.fitView()

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.68))

    const sun = new THREE.DirectionalLight(0xfff4e6, 2.35)
    sun.position.set(50, 80, 60)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.left = -100
    sun.shadow.camera.right = 100
    sun.shadow.camera.top = 80
    sun.shadow.camera.bottom = -80
    this.scene.add(sun)

    const fill = new THREE.DirectionalLight(0x6f7b88, 0.42)
    fill.position.set(-40, 30, -50)
    this.scene.add(fill)

    const water = new THREE.Mesh(
      new THREE.PlaneGeometry(400, 200),
      new THREE.MeshStandardMaterial({
        color: 0xbfc4c2,
        metalness: 0.1,
        roughness: 0.72,
        transparent: true,
        opacity: 0.92
      })
    )
    water.rotation.x = -Math.PI / 2
    water.position.y = -0.15
    water.receiveShadow = true
    water.raycast = () => {}
    this.scene.add(water)

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(400, 200),
      new THREE.MeshStandardMaterial({ color: 0xd9d6cf, roughness: 0.95 })
    )
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -0.2
    ground.receiveShadow = true
    ground.raycast = () => {}
    this.scene.add(ground)

    const grid = new THREE.GridHelper(300, 60, 0x8b8882, 0xc9c6c0)
    const gridMaterial = grid.material as THREE.Material
    gridMaterial.transparent = true
    gridMaterial.opacity = 0.35
    grid.position.y = -0.14
    grid.raycast = () => {}
    this.scene.add(grid)

    this.renderer.domElement.addEventListener('click', this.onCanvasClick)
    window.addEventListener('resize', this.onResize)
    this.resizeObserver = new ResizeObserver(() => this.onResize())
    this.resizeObserver.observe(this.container)
    this.animate()
  }

  async loadModel(request: BridgeSceneModelRequest): Promise<void> {
    const loadSequence = ++this.loadSequence
    this.profile = request.profile
    this.options.onPick?.({
      kind: 'background',
      clientX: 0,
      clientY: 0
    })
    if (this.bridgeModel) {
      this.scene.remove(this.bridgeModel)
      disposeObject(this.bridgeModel)
      this.bridgeModel = null
    }
    if (this.cableGroup) {
      this.scene.remove(this.cableGroup)
      disposeObject(this.cableGroup)
      this.cableGroup = null
    }

    return new Promise((resolve, reject) => {
      const loader = new GLTFLoader()
      loader.load(
        request.fileUrl,
        (gltf) => {
          if (loadSequence !== this.loadSequence) {
            resolve()
            return
          }
          const model = gltf.scene
          applySceneProfile(model, request.profile)
          model.traverse((child: any) => {
            if (!child.isMesh) return
            child.castShadow = true
            child.receiveShadow = true
            if (!child.name || child.name === 'Mesh') child.name = 'bridge_part'
          })
          this.bridgeModel = model
          this.scene.add(model)
          model.updateMatrixWorld(true)

          const overlay = pressureOverlayLayout(request.profile)
          this.pressureDeckY = overlay.y
          this.pressurePlaneWidth = overlay.width
          this.pressurePlaneDepth = overlay.depth
          this.pressurePlaneCenterX = overlay.centerX
          this.pressurePlaneCenterZ = overlay.centerZ
          if (request.addDefaultCables) {
            this.addBundledBridgeStructure(
              request.profile.deck_bounds.min_y,
              request.profile.deck_bounds.max_y
            )
          }
          this.createSensorsFromProfile(request.profile)
          this.ensurePressureOverlay()
          this.updatePressureOverlay()
          this.fitView()
          resolve()
        },
        (progress) => {
          if (progress.total > 0) {
            this.options.onModelProgress?.(
              Math.round((progress.loaded / progress.total) * 100)
            )
          }
        },
        (error) => {
          if (loadSequence !== this.loadSequence) {
            resolve()
            return
          }
          reject(error instanceof Error ? error : new Error('模型加载失败'))
        }
      )
    })
  }

  setSensors(sensors: SensorReading[]) {
    this.sensorsById = new Map(
      sensors.map((sensor) => [sensor.sensor_id, sensor])
    )
    this.updateSensorColors()
  }

  setPressureField(field: PressureField | null) {
    this.pressureField = field
    if (!field || field.coverage === 0) {
      if (this.pressureOverlay) this.pressureOverlay.visible = false
      return
    }
    this.updatePressureOverlay()
  }

  setPressureOverlayEnabled(enabled: boolean) {
    this.pressureOverlayEnabled = enabled
    if (this.pressureOverlay) {
      this.pressureOverlay.visible = enabled && Boolean(this.pressureField?.coverage)
    }
  }

  resetView() {
    this.fitView()
  }

  focusSensor(sensorId: string) {
    const mesh = this.sensorMeshes[sensorId]
    if (!mesh) return
    this.controls.target.copy(mesh.position)
    this.controls.update()
  }

  dispose() {
    this.started = false
    this.loadSequence += 1
    cancelAnimationFrame(this.animationFrame)
    window.removeEventListener('resize', this.onResize)
    this.resizeObserver?.disconnect()
    this.resizeObserver = null
    this.renderer?.domElement.removeEventListener('click', this.onCanvasClick)
    this.controls?.dispose()
    this.clearSensorMarkers()
    if (this.pressureOverlay) {
      disposeObject(this.pressureOverlay)
      this.scene?.remove(this.pressureOverlay)
      this.pressureOverlay = null
    }
    if (this.scene) disposeObject(this.scene)
    this.renderer?.dispose()
    this.renderer?.domElement.remove()
  }

  private readonly onResize = () => {
    if (!this.started) return
    const width = Math.max(1, this.container.clientWidth)
    const height = Math.max(1, this.container.clientHeight)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(width, height)
    this.fitView()
    this.options.onViewportResize?.()
  }

  private fitView() {
    if (!this.camera || !this.controls) return
    const width = Math.max(1, this.container.clientWidth)
    const height = Math.max(1, this.container.clientHeight)
    const fit = sceneCameraFit(this.profile, width / height)
    this.camera.position.set(...fit.position)
    this.controls.target.set(...fit.target)
    this.controls.update()
  }

  private updateSensorColors() {
    for (const [sensorId, sensor] of this.sensorsById) {
      const mesh = this.sensorMeshes[sensorId]
      if (!mesh) continue
      const material = mesh.material as THREE.MeshStandardMaterial
      const color = sensorColor(sensor)
      material.color.copy(color)
      material.emissive.copy(color).multiplyScalar(0.3)
    }
  }

  private clearSensorMarkers() {
    for (const sensorId of Object.keys(this.sensorMeshes)) {
      const mesh = this.sensorMeshes[sensorId]
      this.scene.remove(mesh)
      ;(mesh.material as THREE.Material).dispose()
      const ring = this.sensorRings[sensorId]
      if (ring) {
        this.scene.remove(ring)
        ;(ring.material as THREE.Material).dispose()
      }
    }
    this.sensorMeshes = {}
    this.sensorRings = {}
    this.sensorGeometry?.dispose()
    this.ringGeometry?.dispose()
    this.sensorGeometry = null
    this.ringGeometry = null
  }

  private createSensorsFromProfile(profile: BridgeSceneProfile) {
    this.clearSensorMarkers()
    this.sensorGeometry = new THREE.SphereGeometry(1.65, 16, 16)
    this.ringGeometry = new THREE.RingGeometry(1.5, 2.2, 24)

    for (const [sensorId, anchor] of Object.entries(profile.sensor_anchors)) {
      const mesh = new THREE.Mesh(
        this.sensorGeometry,
        new THREE.MeshStandardMaterial({
          color: 0x111214,
          emissive: 0x111214,
          emissiveIntensity: 0.08,
          metalness: 0.15,
          roughness: 0.38
        })
      )
      mesh.position.set(...anchor.position)
      mesh.castShadow = true
      mesh.name = `sensor_${sensorId}`
      this.scene.add(mesh)
      this.sensorMeshes[sensorId] = mesh

      const ring = new THREE.Mesh(
        this.ringGeometry,
        new THREE.MeshBasicMaterial({
          color: 0x111214,
          transparent: true,
          opacity: 0.32,
          side: THREE.DoubleSide
        })
      )
      ring.position.copy(mesh.position)
      ring.lookAt(this.camera.position)
      ring.name = `ring_${sensorId}`
      this.scene.add(ring)
      this.sensorRings[sensorId] = ring
    }
  }

  private animate = () => {
    this.animationFrame = requestAnimationFrame(this.animate)
    this.controls.update()
    const t = Date.now() * 0.003
    for (const [sensorId, ring] of Object.entries(this.sensorRings)) {
      const scale = 1 + Math.sin(t + sensorId.charCodeAt(2)) * 0.3
      ring.scale.set(scale, scale, 1)
      ring.lookAt(this.camera.position)
      const material = ring.material as THREE.MeshBasicMaterial
      const sensor = this.sensorsById.get(sensorId)
      if (!sensor) continue
      material.color.copy(sensorColor(sensor))
      material.opacity = sensorLevel(sensor) === 'danger'
        ? 0.3 + Math.sin(t * 3) * 0.3
        : 0.4
    }
    this.renderer.render(this.scene, this.camera)
  }

  private ensurePressureOverlay() {
    if (!this.started) return
    if (this.pressureOverlay) {
      this.pressureOverlay.geometry.dispose()
      this.pressureOverlay.geometry = new THREE.PlaneGeometry(
        this.pressurePlaneWidth,
        this.pressurePlaneDepth
      )
      this.pressureOverlay.position.set(
        this.pressurePlaneCenterX,
        this.pressureDeckY,
        this.pressurePlaneCenterZ
      )
      this.pressureOverlay.visible = this.pressureOverlayEnabled
      return
    }
    this.pressureTexture = new THREE.DataTexture(
      new Uint8Array([12, 74, 110, 120]),
      1,
      1,
      THREE.RGBAFormat
    )
    this.pressureTexture.needsUpdate = true
    this.pressureOverlay = new THREE.Mesh(
      new THREE.PlaneGeometry(this.pressurePlaneWidth, this.pressurePlaneDepth),
      new THREE.MeshBasicMaterial({
        map: this.pressureTexture,
        transparent: true,
        opacity: 0.62,
        depthWrite: false,
        side: THREE.DoubleSide
      })
    )
    this.pressureOverlay.rotation.x = -Math.PI / 2
    this.pressureOverlay.position.set(
      this.pressurePlaneCenterX,
      this.pressureDeckY,
      this.pressurePlaneCenterZ
    )
    this.pressureOverlay.renderOrder = 4
    this.pressureOverlay.raycast = () => {}
    this.pressureOverlay.visible = false
    this.scene.add(this.pressureOverlay)
  }

  private updatePressureOverlay() {
    this.ensurePressureOverlay()
    const field = this.pressureField
    if (!this.pressureOverlay || !field || field.coverage === 0) return
    const { nx, nz } = field.grid
    const pixelCount = nx * nz * 4
    if (!this.pressurePixels || this.pressurePixels.length !== pixelCount) {
      this.pressurePixels = new Uint8Array(pixelCount)
    }
    for (let index = 0; index < nx * nz; index += 1) {
      const [red, green, blue] = pressureColor(field.values[index] ?? 0)
      const offset = index * 4
      this.pressurePixels[offset] = red
      this.pressurePixels[offset + 1] = green
      this.pressurePixels[offset + 2] = blue
      this.pressurePixels[offset + 3] = 190
    }

    const image = this.pressureTexture?.image as
      | { width: number; height: number; data: Uint8Array<ArrayBuffer> }
      | undefined
    if (
      !this.pressureTexture ||
      image?.width !== nx ||
      image?.height !== nz
    ) {
      this.pressureTexture?.dispose()
      this.pressureTexture = new THREE.DataTexture(
        this.pressurePixels,
        nx,
        nz,
        THREE.RGBAFormat
      )
      this.pressureTexture.magFilter = THREE.LinearFilter
      this.pressureTexture.minFilter = THREE.LinearFilter
      const material = this.pressureOverlay.material as THREE.MeshBasicMaterial
      material.map = this.pressureTexture
      material.needsUpdate = true
    } else if (image) {
      image.data.set(this.pressurePixels)
    }
    this.pressureTexture.needsUpdate = true
    this.pressureOverlay.visible = this.pressureOverlayEnabled
  }

  private addBundledBridgeStructure(deckBottomY: number, deckTopY: number) {
    const cableMat = new THREE.MeshStandardMaterial({
      color: 0x3d3e40,
      metalness: 0.62,
      roughness: 0.36
    })
    const concreteMat = new THREE.MeshStandardMaterial({
      color: 0x9a968d,
      metalness: 0.04,
      roughness: 0.86
    })
    const anchorMat = new THREE.MeshStandardMaterial({
      color: 0x303133,
      metalness: 0.48,
      roughness: 0.42
    })
    const group = new THREE.Group()
    group.name = 'bundled-structure-repair'

    const towerLegTopY = 53.46
    const towerCapBottomY = 65.45
    const cablePlaneZ = [-3, 3]
    const towerXs = [-60, 60]

    for (const towerX of towerXs) {
      for (const planeZ of cablePlaneZ) {
        const extensionHeight = towerCapBottomY - towerLegTopY
        const extension = new THREE.Mesh(
          new THREE.BoxGeometry(4, extensionHeight, 3),
          concreteMat
        )
        extension.position.set(
          towerX,
          towerLegTopY + extensionHeight / 2,
          planeZ
        )
        extension.name = `pylon-extension-${towerX}-${planeZ}`
        extension.castShadow = true
        extension.receiveShadow = true
        group.add(extension)
      }
    }

    const abutmentHeight = Math.max(deckBottomY, 1)
    for (const abutmentX of [-116.5, 116.5]) {
      const abutment = new THREE.Mesh(
        new THREE.BoxGeometry(7, abutmentHeight, 16),
        concreteMat
      )
      abutment.position.set(abutmentX, abutmentHeight / 2, 0)
      abutment.name = `abutment-${abutmentX}`
      abutment.castShadow = true
      abutment.receiveShadow = true
      group.add(abutment)
    }

    for (const towerX of towerXs) {
      const towardCenter = towerX < 0 ? 1 : -1
      const towerTag = towerX < 0 ? 'L' : 'R'
      const mainAnchors = [1, 2, 3, 4, 5, 5.8].map(
        (step) => towerX + towardCenter * step * 10
      )
      const sideAnchors = [1, 2, 3, 4, 5, 5.8].map(
        (step) => towerX - towardCenter * step * 10
      )

      for (const planeZ of cablePlaneZ) {
        mainAnchors.forEach((deckX, index) => {
          const topY = 54 + index * 2.1
          this.addCableMesh(
            group,
            towerX,
            topY,
            planeZ,
            deckX,
            deckTopY + 0.18,
            planeZ,
            cableMat,
            `stay-${towerTag}-M${index + 1}-${planeZ}`
          )
          this.addAnchorPlate(group, towerX, topY, planeZ, anchorMat)
          this.addAnchorPlate(group, deckX, deckTopY + 0.14, planeZ, anchorMat)
        })
        sideAnchors.forEach((deckX, index) => {
          const topY = 54 + index * 2.1
          this.addCableMesh(
            group,
            towerX,
            topY,
            planeZ,
            deckX,
            deckTopY + 0.18,
            planeZ,
            cableMat,
            `stay-${towerTag}-S${index + 1}-${planeZ}`
          )
          this.addAnchorPlate(group, deckX, deckTopY + 0.14, planeZ, anchorMat)
        })
      }
    }
    this.cableGroup = group
    this.scene.add(group)
  }

  private addAnchorPlate(
    parent: THREE.Object3D,
    x: number,
    y: number,
    z: number,
    material: THREE.Material
  ) {
    const plate = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.34, 1.15), material)
    plate.position.set(x, y, z)
    plate.castShadow = true
    parent.add(plate)
  }

  private addCableMesh(
    parent: THREE.Object3D,
    x1: number,
    y1: number,
    z1: number,
    x2: number,
    y2: number,
    z2: number,
    material: THREE.Material,
    name: string
  ) {
    const start = new THREE.Vector3(x1, y1, z1)
    const end = new THREE.Vector3(x2, y2, z2)
    const direction = end.clone().sub(start)
    const cable = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.12, direction.length(), 10),
      material
    )
    cable.position.copy(start.clone().add(end).multiplyScalar(0.5))
    cable.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      direction.normalize()
    )
    cable.name = name
    cable.castShadow = true
    parent.add(cable)
  }

  private readonly onCanvasClick = (event: MouseEvent) => {
    const rect = this.container.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const candidates: THREE.Object3D[] = Object.values(this.sensorMeshes)
    if (this.bridgeModel) candidates.push(this.bridgeModel)
    const intersects = this.raycaster.intersectObjects(candidates, true)
    if (!intersects.length) {
      this.options.onPick?.({
        kind: 'background',
        clientX: event.clientX,
        clientY: event.clientY
      })
      return
    }

    let clicked: THREE.Object3D | null = intersects[0].object
    let sensorId = ''
    let partName = ''
    let partNameZh = ''
    while (clicked) {
      const name = clicked.name || ''
      if (name.startsWith('sensor_')) {
        sensorId = name.replace('sensor_', '')
        break
      }
      if (['tower_left', 'tower_right', 'deck'].includes(name)) {
        partName = name
        break
      }
      if (name.includes('索塔')) {
        partName = 'tower'
        partNameZh = name.includes('左') ? '左索塔' : '右索塔'
        break
      }
      if (name.includes('主梁') || name.includes('桥面') || name.includes('箱梁')) {
        partName = 'deck'
        partNameZh = '主梁 / 桥面'
        break
      }
      if (name.includes('桥墩')) {
        partName = 'pier'
        partNameZh = name
        break
      }
      if (name.includes('承台')) {
        partName = 'cap'
        partNameZh = name
        break
      }
      if (name.includes('拉索')) {
        partName = 'cable'
        partNameZh = name
        break
      }
      if (name.includes('传感器')) {
        const match = name.match(/S\d+/)
        if (match) sensorId = match[0]
        break
      }
      clicked = clicked.parent
    }

    if (sensorId) {
      this.options.onPick?.({
        kind: 'sensor',
        sensorId,
        clientX: event.clientX,
        clientY: event.clientY
      })
    } else if (partName) {
      this.options.onPick?.({
        kind: 'part',
        partName,
        partNameZh,
        clientX: event.clientX,
        clientY: event.clientY
      })
    } else {
      this.options.onPick?.({
        kind: 'background',
        clientX: event.clientX,
        clientY: event.clientY
      })
    }
  }
}
