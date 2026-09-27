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
      <label class="filter-item">
        <span>站点编码</span>
        <input v-model="keyword" placeholder="按站点编码检索" />
      </label>
      <label class="filter-item">
        <span>站点状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <RouterLink class="link" :to="`/station/${row.id}`">详情</RouterLink>
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              :disabled="acting"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!rowActions(row).length" class="muted-text">无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无观测站点数据，可先登记观测站点</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测站点记录</span>
      <span v-if="notice" class="notice-text">{{ notice }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | boolean | string[] | null>

const ENDPOINT = '/api/station'
const columns = ["站点编码", "站点名称", "站点类别", "经纬度坐标", "海拔高度", "建站年份", "值守方式", "站点状态"]
const statuses = ["待入网", "正常运行", "降级运行", "已停用"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([{ label: '在网站点', value: 0 }, { label: '降级站点', value: 0 }, { label: '停用站点', value: 0 }])
const keyword = ref('')
const statusFilter = ref('')
const acting = ref(false)
const notice = ref('')
const errorMessage = ref('')

function rowActions(row: Row): string[] {
  const value = row.available_actions
  return Array.isArray(value) ? value : []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '观测站点登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (acting.value) {
    return
  }
  acting.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload: { ok?: boolean; message?: string; detail?: string } | null = await response
      .json()
      .catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? payload?.detail ?? '观测站点动作未生效，请稍后重试')
    }
    notice.value = payload.message ?? '观测站点操作已完成'
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测站点操作失败'
  } finally {
    acting.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) {
    query.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('观测站点列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测站点列表读取失败'
  }
}

async function loadStats() {
  try {
    const payload = await fetchJson<{ by_status: Record<string, number> }>(`${ENDPOINT}/summary`)
    const byStatus = payload.by_status ?? {}
    stats.value = [
      { label: '在网站点', value: byStatus['正常运行'] ?? 0 },
      { label: '降级站点', value: byStatus['降级运行'] ?? 0 },
      { label: '停用站点', value: byStatus['已停用'] ?? 0 },
    ]
  } catch {
    // 统计卡读取失败时保留旧值，列表错误信息由 reload 统一提示
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
