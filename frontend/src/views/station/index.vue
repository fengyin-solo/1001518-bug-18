<template>
  <section class="page" data-module="station">
    <header class="page-head">
      <div>
        <h2>观测站点管理</h2>
        <p class="page-desc">维护观测站点，围绕站点编码、站点名称、站点类别、经纬度坐标做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记观测站点</button>
        <button class="btn" type="button" @click="exportRows">导出观测站点清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="notice" class="notice-text" :class="{ 'is-error': noticeType === 'error' }">{{ notice }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '站点状态'">
              <span class="status-pill" :data-status="String(row.status)">{{ row.status ?? '—' }}</span>
            </template>
            <template v-else-if="column === '站点编码'">
              <RouterLink class="link" :to="`/station/${row.id}`">{{ row[column] }}</RouterLink>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRun(action, row) || pendingId === row.id"
              :title="canRun(action, row) ? '' : `当前「${row.status}」状态不能执行${action}`"
              @click="runAction(action, row)"
            >
              {{ pendingId === row.id ? '处理中…' : action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无观测站点数据，可先登记观测站点</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测站点记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type ActionResultPayload = { ok: boolean; message: string; entry: Row | null }

const ENDPOINT = '/api/station'
const columns = ["站点编码", "站点名称", "站点类别", "经纬度坐标", "海拔高度", "建站年份", "值守方式", "站点状态"]
const actions = ["办理入网", "标记降级", "停用站点"] as const

// 与后端状态机保持同一套可执行口径，按钮置灰只是防呆，真正的约束仍在服务端
const ACTION_SOURCES: Record<string, string[]> = {
  办理入网: ["待入网"],
  标记降级: ["正常运行"],
  停用站点: ["正常运行", "降级运行"],
}
const ACTION_NOTICE: Record<string, string> = {
  停用站点: '停用后站点进入收尾状态，不能直接重新入网，确认停用该站点吗？',
  标记降级: '降级将按异常口径计入概览看板，确认标记该站点降级吗？',
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '待入网', value: 0 },
  { label: '在网站点', value: 0 },
  { label: '降级站点', value: 0 },
  { label: '停用站点', value: 0 },
])
const errorMessage = ref('')
const notice = ref('')
const noticeType = ref<'ok' | 'error'>('ok')
const pendingId = ref<number | null>(null)
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

let noticeTimer: ReturnType<typeof setTimeout> | undefined

function showNotice(message: string, type: 'ok' | 'error' = 'ok') {
  notice.value = message
  noticeType.value = type
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => { notice.value = '' }, 4000)
}

function canRun(action: string, row: Row) {
  return ACTION_SOURCES[action]?.includes(String(row.status)) ?? false
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '观测站点登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  // 重复点击 / 并发点击：同一站点在途动作未结束前直接忽略，避免点错站点导致状态错位
  if (pendingId.value !== null) return
  if (!canRun(action, row)) {
    showNotice(`站点当前为「${row.status}」，不能执行${action}`, 'error')
    return
  }
  if (ACTION_NOTICE[action] && !window.confirm(ACTION_NOTICE[action])) return

  const targetId = Number(row.id)
  pendingId.value = targetId
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${targetId}/actions`, {
      method: 'POST',
      // 后端 EntryPayload 约定动作放在 values 里；裸传 { action } 会被静默丢弃
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('观测站点动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as ActionResultPayload
    // HTTP 200 不代表业务成功，必须看 ok；失败时绝不改动本地状态
    if (!payload.ok || !payload.entry) {
      showNotice(payload.message || '观测站点动作未生效', 'error')
      return
    }
    // 按 id 精确回填服务端返回的状态，不依赖行序，点错站点也不会错位
    patchRow(payload.entry)
    await reloadStats()
    showNotice(payload.message || '操作成功')
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '观测站点操作失败', 'error')
  } finally {
    pendingId.value = null
  }
}

function patchRow(updated: Row) {
  const index = rows.value.findIndex((item) => item.id === updated.id)
  if (index >= 0) {
    rows.value.splice(index, 1, { ...rows.value[index], ...updated })
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const data = await response.json() as Record<string, number>
    stats.value = [
      { label: '待入网', value: data.pending ?? 0 },
      { label: '在网站点', value: data.online ?? 0 },
      { label: '降级站点', value: data.degraded ?? 0 },
      { label: '停用站点', value: data.disabled ?? 0 },
    ]
  } catch {
    // 统计卡读取失败不影响列表，页面刷新后自然恢复
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('观测站点列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测站点列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.notice-text {
  margin: 8px 0;
  padding: 8px 12px;
  border-radius: 6px;
  background: #ecfdf3;
  color: #027a48;
  font-size: 13px;
}
.notice-text.is-error {
  background: #fef3f2;
  color: #b42318;
}
.status-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
}
.status-pill[data-status='待入网'] { background: #f2f4f7; color: #475467; }
.status-pill[data-status='正常运行'] { background: #ecfdf3; color: #027a48; }
.status-pill[data-status='降级运行'] { background: #fffaeb; color: #b54708; }
.status-pill[data-status='已停用'] { background: #fef3f2; color: #b42318; }
.link:disabled {
  color: #98a2b3;
  cursor: not-allowed;
}
</style>
