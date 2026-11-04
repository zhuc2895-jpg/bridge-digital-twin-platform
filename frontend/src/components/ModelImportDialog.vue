<template>
  <div v-if="modelValue" class="dialog-backdrop" @click.self="close">
    <section class="model-dialog" role="dialog" aria-modal="true" aria-label="桥梁模型导入">
      <header class="dialog-header">
        <div>
          <h2>桥梁模型导入</h2>
          <p>支持自包含 GLB / glTF 2.0，导入后可以直接切换到新模型</p>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" @click="close">×</button>
      </header>

      <div class="dialog-body">
        <form class="upload-form" @submit.prevent="submitImport">
          <label class="field">
            <span>模型文件</span>
            <input
              ref="fileInputRef"
              type="file"
              accept=".glb,.gltf,model/gltf-binary,model/gltf+json"
              @change="onFileChange"
            />
          </label>
          <label class="field">
            <span>显示名称</span>
            <input v-model.trim="displayName" type="text" maxlength="120" placeholder="例如：浍河大桥 BIM" />
          </label>
          <label class="field">
            <span>Scene Profile（可选 JSON）</span>
            <input ref="profileInputRef" type="file" accept=".json,application/json" @change="onProfileFileChange" />
          </label>
          <label class="toggle-field">
            <input v-model="activateAfterImport" type="checkbox" />
            <span>导入后立即激活并在 3D 视图中加载</span>
          </label>
          <div class="upload-actions">
            <span class="file-hint">{{ selectedFile ? `${selectedFile.name} · ${formatBytes(selectedFile.size)}` : '尚未选择文件' }}</span>
            <button class="primary-button" type="submit" :disabled="!selectedFile || busy">
              {{ busy ? '正在导入…' : '导入模型' }}
            </button>
          </div>
          <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
        </form>

        <div class="model-list-section">
          <div class="list-header">
            <div>
              <h3>已导入模型</h3>
              <span>{{ models.length }} 个模型</span>
            </div>
            <button class="secondary-button" type="button" :disabled="busy" @click="loadModels">刷新</button>
          </div>

          <div v-if="loading" class="empty-list">正在读取模型列表…</div>
          <div v-else-if="models.length === 0" class="empty-list">
            暂无导入模型，当前使用内置桥梁模型。
          </div>
          <div v-else class="model-list">
            <article v-for="model in models" :key="model.model_id" class="model-item" :class="{ active: model.active }">
              <div class="model-main">
                <div class="model-name">
                  {{ model.name }}
                  <span v-if="model.active" class="active-badge">使用中</span>
                </div>
                <div class="model-meta">
                  {{ model.format.toUpperCase() }} · {{ formatBytes(model.size_bytes) }} ·
                  {{ formatDate(model.created_at) }}
                </div>
              </div>
              <div class="model-actions">
                <button
                  class="small-button"
                  type="button"
                  :disabled="busy"
                  @click="chooseProfileReplacement(model)"
                >
                  更新 Profile
                </button>
                <button
                  class="small-button"
                  type="button"
                  :disabled="busy || model.active"
                  @click="activateModel(model)"
                >
                  {{ model.active ? '已激活' : '激活' }}
                </button>
                <button class="small-button danger" type="button" :disabled="busy" @click="deleteModel(model)">
                  删除
                </button>
              </div>
            </article>
          </div>

          <button class="bundled-button" type="button" :disabled="busy || !hasImportedActive" @click="useBundledModel">
            使用内置桥梁模型
          </button>
          <input
            ref="profileReplacementInput"
            class="hidden-input"
            type="file"
            accept=".json,application/json"
            @change="replaceProfileFile"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiFetch } from '../api'
import type { ActiveBridgeModel, BridgeModel } from '../types/live'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  activated: [fileUrl: string, name: string]
}>()

const models = ref<BridgeModel[]>([])
const selectedFile = ref<File | null>(null)
const profileFile = ref<File | null>(null)
const profileReplaceTarget = ref<BridgeModel | null>(null)
const displayName = ref('')
const activateAfterImport = ref(true)
const busy = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const fileInputRef = ref<HTMLInputElement>()
const profileInputRef = ref<HTMLInputElement>()
const profileReplacementInput = ref<HTMLInputElement>()
const hasImportedActive = computed(() => models.value.some(model => model.active))

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      errorMessage.value = ''
      loadModels()
    }
  }
)

function close() {
  if (busy.value) return
  emit('update:modelValue', false)
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
  if (selectedFile.value && !displayName.value) {
    displayName.value = selectedFile.value.name.replace(/\.(glb|gltf)$/i, '')
  }
}

function onProfileFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  profileFile.value = input.files?.[0] || null
}

async function loadModels() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch('/api/models')
    if (!response.ok) throw new Error(await errorText(response))
    const payload = (await response.json()) as { models: BridgeModel[] }
    models.value = payload.models || []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取模型列表失败'
  } finally {
    loading.value = false
  }
}

async function submitImport() {
  if (!selectedFile.value || busy.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    if (profileFile.value) form.append('profile_file', profileFile.value)
    if (displayName.value) form.append('name', displayName.value)
    form.append('activate', String(activateAfterImport.value))
    const response = await apiFetch('/api/models/import', { method: 'POST', body: form })
    if (!response.ok) throw new Error(await errorText(response))
    const payload = (await response.json()) as { model: BridgeModel }
    selectedFile.value = null
    profileFile.value = null
    displayName.value = ''
    if (fileInputRef.value) fileInputRef.value.value = ''
    if (profileInputRef.value) profileInputRef.value.value = ''
    await loadModels()
    if (payload.model.active) {
      emit('activated', payload.model.file_url, payload.model.name)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模型导入失败'
  } finally {
    busy.value = false
  }
}

function chooseProfileReplacement(model: BridgeModel) {
  profileReplaceTarget.value = model
  profileReplacementInput.value?.click()
}

async function replaceProfileFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const target = profileReplaceTarget.value
  if (!file || !target) return
  busy.value = true
  errorMessage.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await apiFetch(`/api/models/${target.model_id}/profile`, {
      method: 'POST',
      body: form
    })
    if (!response.ok) throw new Error(await errorText(response))
    await loadModels()
    emit('activated', target.file_url, target.name)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '更新 Scene Profile 失败'
  } finally {
    busy.value = false
    profileReplaceTarget.value = null
    input.value = ''
  }
}

async function activateModel(model: BridgeModel) {
  busy.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch(`/api/models/${model.model_id}/activate`, { method: 'POST' })
    if (!response.ok) throw new Error(await errorText(response))
    await loadModels()
    emit('activated', model.file_url, model.name)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '激活模型失败'
  } finally {
    busy.value = false
  }
}

async function deleteModel(model: BridgeModel) {
  if (!window.confirm(`确认删除模型“${model.name}”？`)) return
  busy.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch(`/api/models/${model.model_id}`, { method: 'DELETE' })
    if (!response.ok) throw new Error(await errorText(response))
    const wasActive = model.active
    await loadModels()
    if (wasActive) emit('activated', '/models/huihe_bridge.glb', '内置模型')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '删除模型失败'
  } finally {
    busy.value = false
  }
}

async function useBundledModel() {
  busy.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch('/api/models/deactivate', { method: 'POST' })
    if (!response.ok) throw new Error(await errorText(response))
    const payload = (await response.json()) as ActiveBridgeModel
    await loadModels()
    emit('activated', payload.file_url, '内置模型')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '切换内置模型失败'
  } finally {
    busy.value = false
  }
}

async function errorText(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    return typeof payload.detail === 'string' ? payload.detail : `请求失败 (${response.status})`
  } catch {
    return `请求失败 (${response.status})`
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(17, 18, 20, 0.58);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
}
.model-dialog {
  width: min(820px, 100%);
  max-height: min(720px, 92vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--ink, #111214);
  border-radius: 0;
  background: var(--paper-hi, #f4f3ef);
  box-shadow: 14px 14px 0 rgba(17, 18, 20, 0.18);
}
.dialog-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--ink, #111214);
}
.dialog-header h2 { margin: 0; color: var(--ink, #111214); font-family: var(--display, sans-serif); font-size: 20px; font-weight: 800; letter-spacing: 0.02em; }
.dialog-header p { margin: 6px 0 0; color: var(--mute, #77746d); font-family: var(--cjk, sans-serif); font-size: 9px; }
.icon-button { width: 30px; height: 30px; flex: none; border: 1px solid var(--ink, #111214); border-radius: 0; background: transparent; color: var(--ink, #111214); cursor: pointer; font-size: 18px; line-height: 1; }
.icon-button:hover { background: var(--ink, #111214); color: var(--paper, #f4f3ef); }
.dialog-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); gap: 22px; overflow: auto; padding: 18px 20px 22px; }
.upload-form, .model-list-section { min-width: 0; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 13px; color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 7px; letter-spacing: 0.5px; }
.field input[type='text'], .field input[type='file'] { width: 100%; padding: 9px 10px; border: 1px solid var(--line, rgba(17, 18, 20, 0.18)); border-radius: 0; background: var(--paper, #e7e5e1); color: var(--ink, #111214); font-family: var(--cjk, sans-serif); font-size: 10px; }
.field input:focus { border-color: var(--ink, #111214); outline: 0; }
.toggle-field { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 14px; color: var(--ink, #111214); font-family: var(--cjk, sans-serif); font-size: 9px; line-height: 1.45; }
.toggle-field input { accent-color: var(--ink, #111214); }
.upload-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.file-hint { min-width: 0; overflow: hidden; color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 6.5px; white-space: nowrap; text-overflow: ellipsis; }
.primary-button, .secondary-button, .small-button, .bundled-button { padding: 7px 11px; border: 1px solid var(--ink, #111214); border-radius: 0; background: transparent; color: var(--ink, #111214); cursor: pointer; font-family: var(--mono, monospace); font-size: 7px; letter-spacing: 0.5px; }
.primary-button { background: var(--ink, #111214); color: var(--paper, #f4f3ef); }
.primary-button:hover:not(:disabled) { background: var(--lime, #b9e432); color: var(--ink, #111214); }
.secondary-button:hover:not(:disabled), .small-button:hover:not(:disabled), .bundled-button:hover:not(:disabled) { background: var(--ink, #111214); color: var(--paper, #f4f3ef); }
.small-button.danger { border-color: var(--red, #e23b12); color: var(--red, #e23b12); }
.small-button.danger:hover:not(:disabled) { background: var(--red, #e23b12); color: var(--paper, #f4f3ef); }
.primary-button:disabled, .secondary-button:disabled, .small-button:disabled, .bundled-button:disabled { opacity: 0.35; cursor: not-allowed; }
.error-message { margin: 12px 0 0; color: var(--red, #e23b12); font-family: var(--cjk, sans-serif); font-size: 9px; line-height: 1.5; }
.list-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.list-header h3 { margin: 0; color: var(--ink, #111214); font-family: var(--display, sans-serif); font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }
.list-header span { color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 6.5px; }
.empty-list { min-height: 120px; display: flex; align-items: center; justify-content: center; padding: 18px; border: 1px dashed var(--faint, #b7b3ab); background: var(--paper, #e7e5e1); color: var(--mute, #77746d); font-family: var(--cjk, sans-serif); font-size: 9px; line-height: 1.6; text-align: center; }
.model-list { display: flex; flex-direction: column; max-height: 250px; overflow: auto; }
.model-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 10px; border-top: 1px solid var(--line, rgba(17, 18, 20, 0.18)); background: transparent; }
.model-item:last-child { border-bottom: 1px solid var(--line, rgba(17, 18, 20, 0.18)); }
.model-item.active { border-left: 3px solid var(--lime, #b9e432); background: rgba(185, 228, 50, 0.08); }
.model-main { min-width: 0; }
.model-name { overflow: hidden; color: var(--ink, #111214); font-family: var(--cjk, sans-serif); font-size: 9px; font-weight: 600; white-space: nowrap; text-overflow: ellipsis; }
.active-badge { margin-left: 6px; padding: 1px 5px; background: var(--ink, #111214); color: var(--lime, #b9e432); font-family: var(--mono, monospace); font-size: 5.8px; letter-spacing: 0.4px; }
.model-meta { margin-top: 3px; color: var(--mute, #77746d); font-family: var(--mono, monospace); font-size: 6px; }
.model-actions { display: flex; flex: none; gap: 5px; }
.bundled-button { width: 100%; margin-top: 12px; background: transparent; }
.hidden-input { display: none; }
@media (max-width: 720px) {
  .dialog-body { grid-template-columns: 1fr; }
}
</style>
