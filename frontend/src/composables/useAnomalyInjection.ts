export async function injectAnomaly(sensorId: string): Promise<boolean> {
  try {
    const response = await fetch(
      `http://127.0.0.1:8000/api/analysis/inject-anomaly?sensor_id=${encodeURIComponent(sensorId)}`,
      { method: 'POST' }
    )
    return response.ok
  } catch {
    return false
  }
}
