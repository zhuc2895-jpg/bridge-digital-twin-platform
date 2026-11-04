export type MeasurementRoleKey =
  | 'primary_strain'
  | 'tower_displacement'
  | 'cable_acceleration'

export interface MeasurementRoleDefinition {
  key: MeasurementRoleKey
  fallbackLabel: string
  color: string
  lineWidth: number
  yAxisIndex: number
  area?: boolean
}

export interface MeasurementSample {
  sensor_id: string
  value: number
}

export interface MeasurementTimelineSeries {
  key: MeasurementRoleKey
  label: string
  color: string
  lineWidth: number
  yAxisIndex: number
  area: boolean
  data: Array<number | null>
}

export interface MeasurementTimelineSnapshot {
  times: string[]
  series: MeasurementTimelineSeries[]
}

export const MEASUREMENT_ROLES: MeasurementRoleDefinition[] = [
  {
    key: 'primary_strain',
    fallbackLabel: '跨中应变',
    color: '#111214',
    lineWidth: 1.7,
    yAxisIndex: 0,
    area: true
  },
  {
    key: 'tower_displacement',
    fallbackLabel: '塔顶位移',
    color: '#ff6a00',
    lineWidth: 1.3,
    yAxisIndex: 0
  },
  {
    key: 'cable_acceleration',
    fallbackLabel: '拉索振动',
    color: '#8c9e2e',
    lineWidth: 1.3,
    yAxisIndex: 1
  }
]

type RoleIds = Partial<Record<MeasurementRoleKey, string>>

function normalizedRoleIds(roleIds: RoleIds): Record<MeasurementRoleKey, string> {
  return {
    primary_strain: roleIds.primary_strain || '',
    tower_displacement: roleIds.tower_displacement || '',
    cable_acceleration: roleIds.cable_acceleration || ''
  }
}

export class MeasurementTimeline {
  private readonly maxPoints: number
  private identity = ''
  private roleIds = normalizedRoleIds({})
  private times: string[] = []
  private values: Record<MeasurementRoleKey, Array<number | null>> = {
    primary_strain: [],
    tower_displacement: [],
    cable_acceleration: []
  }

  constructor(maxPoints = 60) {
    this.maxPoints = maxPoints
  }

  configure(identity: string, roleIds: RoleIds) {
    const nextIds = normalizedRoleIds(roleIds)
    const changed = identity !== this.identity || MEASUREMENT_ROLES.some(
      (role) => nextIds[role.key] !== this.roleIds[role.key]
    )
    if (!changed) return false
    this.identity = identity
    this.roleIds = nextIds
    this.reset()
    return true
  }

  reset() {
    this.times = []
    this.values = {
      primary_strain: [],
      tower_displacement: [],
      cable_acceleration: []
    }
  }

  appendSensors(samples: Iterable<MeasurementSample>, time: string) {
    const byId = new Map<string, MeasurementSample>()
    for (const sample of samples) byId.set(sample.sensor_id, sample)
    this.appendResolved(byId, time)
  }

  appendSnapshot(snapshot: Record<string, MeasurementSample>, time: string) {
    const byId = new Map<string, MeasurementSample>()
    for (const [sensorId, sample] of Object.entries(snapshot)) {
      byId.set(sensorId, sample)
    }
    this.appendResolved(byId, time)
  }

  snapshot(): MeasurementTimelineSnapshot {
    return {
      times: [...this.times],
      series: this.seriesDefinitions().map((role) => ({
        key: role.key,
        label: role.label,
        color: role.color,
        lineWidth: role.lineWidth,
        yAxisIndex: role.yAxisIndex,
        area: Boolean(role.area),
        data: [...this.values[role.key]]
      }))
    }
  }

  seriesDefinitions(): Array<MeasurementRoleDefinition & { label: string }> {
    return MEASUREMENT_ROLES.map((role) => {
      const sensorId = this.roleIds[role.key]
      return {
        ...role,
        label: sensorId
          ? `${sensorId} ${role.fallbackLabel}`
          : `${role.fallbackLabel} UNAVAILABLE`
      }
    })
  }

  private appendResolved(byId: Map<string, MeasurementSample>, time: string) {
    const next = MEASUREMENT_ROLES.map((role) => {
      const sensorId = this.roleIds[role.key]
      const sample = sensorId ? byId.get(sensorId) : undefined
      return sample ? sample.value : null
    })
    if (next.every((value) => value === null)) return

    this.times.push(time)
    MEASUREMENT_ROLES.forEach((role, index) => {
      this.values[role.key].push(next[index])
    })
    if (this.times.length <= this.maxPoints) return

    const overflow = this.times.length - this.maxPoints
    this.times.splice(0, overflow)
    for (const role of MEASUREMENT_ROLES) {
      this.values[role.key].splice(0, overflow)
    }
  }
}
