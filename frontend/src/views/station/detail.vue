<template>
  <section class="page" data-module="station-detail">
    <header class="page-head">
      <div>
        <h2>观测站点详情</h2>
        <p class="page-desc">站点状态与列表、概览看板来自同一份数据；下方保留每次成功流转的操作记录。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
        <button class="btn ghost" type="button" @click="load">刷新</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="entry">
      <div class="detail-status">
        <span>当前状态：</span>
        <span class="status-pill" :data-status="String(entry.status)">{{ entry.status }}</span>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="column in detailFields" :key="column">
            <th>{{ column }}</th>
            <td>
              <span v-if="column === '站点状态'" class="status-pill" :data-status="String(entry.status)">{{ entry.status }}</span>
              <template v-else>{{ entry[column] ?? '—' }}</template>
            </td>
          </tr>
          <tr>
            <th>状态标记</th>
            <td>{{ entry.abnormal ? '异常收尾（降级/停用计入异常量）' : entry.pending ? '待入网（计入待处理）' : '正常运行' }}</td>
          </tr>
        </tbody>
      </table>

      <h3 class="history-title">操作记录</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>序号</th><th>动作</th><th>变更前</th><th>变更后</th><th>操作人</th><th>操作时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in history" :key="record.seq">
            <td>{{ record.seq }}</td>
            <td>{{ record.action }}</td>
            <td><span class="status-pill" :data-status="record.from">{{ record.from }}</span></td>
            <td><span class="status-pill" :data-status="record.to">{{ record.to }}</span></td>
            <td>{{ record.operator }}</td>
            <td>{{ record.time }}</td>
          </tr>
          <tr v-if="!history.length">
            <td colspan="6" class="empty-state">暂无操作记录（仅成功的状态流转会入账，失败与重复点击不留痕）</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type HistoryRecord = {
  seq: number
  action: string
  from: string
  to: string
  operator: string
  time: string
}

const route = useRoute()
const router = useRouter()

const ENDPOINT = `/api/station/${String(route.params.id)}`
const detailFields = ["站点编码", "站点名称", "站点类别", "经纬度坐标", "海拔高度", "建站年份", "值守方式", "站点状态"]

const entry = ref<Row | null>(null)
const history = ref<HistoryRecord[]>([])
const errorMessage = ref('')

function goBack() {
  void router.push('/station')
}

async function load() {
  errorMessage.value = ''
  try {
    const [detailRes, historyRes] = await Promise.all([
      request(ENDPOINT),
      request(`${ENDPOINT}/history`),
    ])
    if (!detailRes.ok) {
      throw new Error(detailRes.status === 404 ? '观测站点不存在或已归档' : '站点详情读取失败')
    }
    entry.value = await detailRes.json()
    if (historyRes.ok) {
      const payload = await historyRes.json() as { items?: HistoryRecord[] }
      history.value = payload.items ?? []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '站点详情读取失败'
  }
}

onMounted(load)
</script>

<style scoped>
.detail-status {
  margin: 12px 0;
  font-size: 14px;
  color: #344054;
}
.detail-table th {
  width: 160px;
}
.history-title {
  margin: 24px 0 8px;
  font-size: 15px;
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
</style>
