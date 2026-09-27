<template>
  <section class="page" data-module="station">
    <header class="page-head">
      <div>
        <h2>观测站点详情</h2>
        <p class="page-desc">与列表、概览看板共用同一份状态口径，并保留每次状态流转的操作记录。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/station">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">站点状态</span>
          <strong class="stat-value">{{ show(entry['站点状态']) }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">待处理</span>
          <strong class="stat-value">{{ entry.pending ? '是' : '否' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">异常</span>
          <strong class="stat-value">{{ entry.abnormal ? '是' : '否' }}</strong>
        </article>
      </div>

      <table class="data-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>{{ show(entry[field]) }}</td>
          </tr>
        </tbody>
      </table>

      <h3>操作记录</h3>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>动作</th><th>状态变化</th></tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in history" :key="index">
            <td>{{ item.time }}</td>
            <td>{{ item.action }}</td>
            <td>{{ item.from }} → {{ item.to }}</td>
          </tr>
          <tr v-if="!history.length">
            <td colspan="3" class="empty-state">暂无操作记录</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { fetchJson } from '@/api/client'

type HistoryItem = { time: string; action: string; from: string; to: string }
type StationEntry = {
  pending?: boolean
  abnormal?: boolean
  history?: HistoryItem[]
  [key: string]: unknown
}

const detailFields = ["站点编码", "站点名称", "站点类别", "经纬度坐标", "海拔高度", "建站年份", "值守方式", "站点状态"]

const route = useRoute()
const entry = ref<StationEntry | null>(null)
const errorMessage = ref('')

const history = computed<HistoryItem[]>(() => entry.value?.history ?? [])

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return String(value)
}

onMounted(async () => {
  try {
    entry.value = await fetchJson<StationEntry>(`/api/station/${route.params.id}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测站点详情读取失败'
  }
})
</script>
