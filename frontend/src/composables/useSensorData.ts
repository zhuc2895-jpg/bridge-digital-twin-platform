import { computed, type Ref } from 'vue'
import type { SensorData } from './useWebSocket'

/**
 * 传感器数据管理
 * 按类型/位置分组、健康状态计算
 */

export function useSensorData(sensorData: Ref<SensorData[]>) {
  // 按类型分组
  const strainSensors = computed(() =>
    sensorData.value.filter(s => s.type === 'strain')
  )
  const displacementSensors = computed(() =>
    sensorData.value.filter(s => s.type === 'displacement')
  )
  const accelerationSensors = computed(() =>
    sensorData.value.filter(s => s.type === 'acceleration')
  )
  const temperatureSensors = computed(() =>
    sensorData.value.filter(s => s.type === 'temperature')
  )

  // 按位置分组
  const sensorsByPosition = computed(() => {
    const map: Record<string, SensorData[]> = {}
    sensorData.value.forEach(s => {
      if (!map[s.position]) map[s.position] = []
      map[s.position].push(s)
    })
    return map
  })

  // 健康状态映射（基于应力/位移值）
  const healthStatus = computed(() => {
    const status: Record<string, { color: string; label: string; value: number }> = {}
    sensorData.value.forEach(s => {
      if (s.type === 'strain') {
        if (s.value > 600) status[s.sensor_id] = { color: '#ff4d4f', label: '危险', value: s.value }
        else if (s.value > 450) status[s.sensor_id] = { color: '#fa8c16', label: '警告', value: s.value }
        else if (s.value > 300) status[s.sensor_id] = { color: '#fadb14', label: '注意', value: s.value }
        else status[s.sensor_id] = { color: '#52c41a', label: '正常', value: s.value }
      } else if (s.type === 'displacement') {
        if (s.value > 80) status[s.sensor_id] = { color: '#ff4d4f', label: '危险', value: s.value }
        else if (s.value > 50) status[s.sensor_id] = { color: '#fa8c16', label: '警告', value: s.value }
        else if (s.value > 30) status[s.sensor_id] = { color: '#fadb14', label: '注意', value: s.value }
        else status[s.sensor_id] = { color: '#52c41a', label: '正常', value: s.value }
      } else {
        status[s.sensor_id] = { color: '#52c41a', label: '正常', value: s.value }
      }
    })
    return status
  })

  // 获取指定传感器的历史数据（用于图表）
  async function fetchHistory(sensorId: string, minutes: number = 60) {
    try {
      const res = await fetch(`http://localhost:8000/api/sensors/${sensorId}/history?minutes=${minutes}`)
      return await res.json()
    } catch (e) {
      console.error('Fetch history error:', e)
      return { data: [] }
    }
  }

  return {
    strainSensors,
    displacementSensors,
    accelerationSensors,
    temperatureSensors,
    sensorsByPosition,
    healthStatus,
    fetchHistory
  }
}
