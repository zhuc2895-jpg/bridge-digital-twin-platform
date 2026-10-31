import { ref } from 'vue'

const pendingSensorIds = ref<Set<string>>(new Set())

export function usePendingSensors() {
  function markSensorPending(sensorId: string) {
    pendingSensorIds.value = new Set([...pendingSensorIds.value, sensorId])
  }

  function clearSensorPending(sensorId: string) {
    pendingSensorIds.value = new Set(
      [...pendingSensorIds.value].filter(id => id !== sensorId)
    )
  }

  function clearReceivedSensors(sensors: Array<{ sensor_id: string }>) {
    const receivedIds = new Set(sensors.map(sensor => sensor.sensor_id))
    pendingSensorIds.value = new Set(
      [...pendingSensorIds.value].filter(sensorId => !receivedIds.has(sensorId))
    )
  }

  return {
    pendingSensorIds,
    markSensorPending,
    clearSensorPending,
    clearReceivedSensors
  }
}
