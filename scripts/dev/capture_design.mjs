import fs from 'node:fs'

const url = process.argv[2] || 'http://127.0.0.1:8000/app'
const output = process.argv[3] || 'assets/screenshots/design-review-live.png'
const waitMs = Number(process.argv[4] || 7000)
const debugBase = process.env.CDP_BASE || 'http://127.0.0.1:9222'

const target = await fetch(`${debugBase}/json/new?about:blank`, { method: 'PUT' }).then((response) => response.json())
const socket = new WebSocket(target.webSocketDebuggerUrl)
const pending = new Map()
let nextId = 1

socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data)
  if (!message.id) return
  const handler = pending.get(message.id)
  if (!handler) return
  pending.delete(message.id)
  if (message.error) handler.reject(new Error(message.error.message))
  else handler.resolve(message.result)
})

await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

function send(method, params = {}) {
  const id = nextId++
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

try {
  await send('Page.enable')
  await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1600,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false
  })
  await send('Page.navigate', { url })
  await new Promise((resolve) => setTimeout(resolve, waitMs))
  const screenshot = await send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false
  })
  fs.writeFileSync(output, Buffer.from(screenshot.data, 'base64'))
  const state = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      title: document.title,
      sensors: document.querySelectorAll('.sensor-cell').length,
      pressureText: document.querySelector('.empty-cloud')?.textContent || 'rendered',
      bodyWidth: document.body.scrollWidth,
      bodyHeight: document.body.scrollHeight
    })`,
    returnByValue: true
  })
  console.log(state.result.value)
} finally {
  await fetch(`${debugBase}/json/close/${target.id}`).catch(() => {})
  socket.close()
}

