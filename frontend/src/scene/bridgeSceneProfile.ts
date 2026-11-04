import type { Object3D } from 'three'
import type { BridgeSceneProfile } from '../types/live'

export interface PressureOverlayLayout {
  width: number
  depth: number
  centerX: number
  centerZ: number
  y: number
}

export interface SceneCameraFit {
  position: [number, number, number]
  target: [number, number, number]
}

export function applySceneProfile(model: Object3D, profile: BridgeSceneProfile) {
  const transform = profile.model_transform
  model.position.set(...transform.translation)
  model.quaternion.set(...transform.rotation)
  model.scale.set(...transform.scale)
  model.updateMatrixWorld(true)
}

export function pressureOverlayLayout(profile: BridgeSceneProfile): PressureOverlayLayout {
  const deck = profile.deck_bounds
  return {
    width: deck.max_x - deck.min_x,
    depth: deck.max_z - deck.min_z,
    centerX: (deck.min_x + deck.max_x) / 2,
    centerZ: (deck.min_z + deck.max_z) / 2,
    y: deck.max_y + 0.35
  }
}

export function sceneCameraFit(
  profile: BridgeSceneProfile | null,
  viewerAspect: number
): SceneCameraFit {
  const deck = profile?.deck_bounds
  const length = deck ? deck.max_x - deck.min_x : 240
  const width = deck ? deck.max_z - deck.min_z : 20
  const centerX = deck ? (deck.min_x + deck.max_x) / 2 : 0
  const centerY = deck ? (deck.min_y + deck.max_y) / 2 : 15
  const centerZ = deck ? (deck.min_z + deck.max_z) / 2 : 0
  const scale = Math.max(0.35, length / 240, width / 20, 1.6 / viewerAspect)
  return {
    position: [
      centerX + 150 * scale,
      centerY + 65 * scale,
      centerZ + 200 * scale
    ],
    target: [centerX, centerY, centerZ]
  }
}

export function profileDisplayString(
  profile: BridgeSceneProfile | null,
  key: string,
  fallback = ''
): string {
  const value = profile?.display?.[key]
  return typeof value === 'string' && value.trim() ? value : fallback
}

