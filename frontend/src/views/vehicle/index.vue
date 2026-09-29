<template>
  <section class="page" data-module="vehicle">
    <header class="page-head">
      <div>
        <h2>特种车辆管理</h2>
        <p class="page-desc">按年检日期、车辆年限与燃油量核检出勤资格；年检到期前 15 天内或已超期的不允许出勤，燃油低于下限的先补油再排。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记特种车辆</button>
        <button class="btn" type="button" @click="exportRows">导出车辆清单</button>
        <button class="btn" type="button" @click="exportDispatch">导出当日出勤单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'stat-available': item.label === '可用车辆' }">{{ item.value }}</strong>
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
            <span v-if="column === '不可调度原因'">
              <span v-if="row['不可调度原因'] && (row['不可调度原因'] as string[]).length" class="reason-text">
                {{ (row['不可调度原因'] as string[]).join('；') }}
              </span>
              <span v-else>—</span>
            </span>
            <span v-else-if="column === '调度状态'">
              <span class="dispatch-tag" :class="dispatchTagClass(row['调度状态'] as string)">{{ row['调度状态'] ?? '—' }}</span>
            </span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无特种车辆数据，可先登记特种车辆</td>
        </tr>
      </tbody>
    </table>

    <section class="record-section">
      <div class="record-head">
        <h3>出勤清单（当日）</h3>
        <span class="record-count">共 {{ dispatchRecords.length }} 辆</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>车辆编号</th>
            <th>车辆类型</th>
            <th>出勤日期</th>
            <th>出车时间</th>
            <th>收车时间</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in dispatchRecords" :key="String(record.id)">
            <td>{{ record['车辆编号'] ?? '—' }}</td>
            <td>{{ record['车辆类型'] ?? '—' }}</td>
            <td>{{ record['出勤日期'] ?? '—' }}</td>
            <td>{{ record['出车时间'] ?? '—' }}</td>
            <td>{{ record['收车时间'] ?? '—' }}</td>
            <td>{{ record['状态'] ?? '—' }}</td>
          </tr>
          <tr v-if="!dispatchRecords.length">
            <td colspan="6" class="empty-state">当日暂无出勤记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="record-section">
      <div class="record-head">
        <h3>维修记录</h3>
        <span class="record-count">共 {{ maintenanceRecords.length }} 条（每辆车仅保留最近一次）</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>车辆编号</th>
            <th>维修日期</th>
            <th>维修内容</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in maintenanceRecords" :key="String(record.id)">
            <td>{{ record['车辆编号'] ?? '—' }}</td>
            <td>{{ record['维修日期'] ?? '—' }}</td>
            <td>{{ record['维修内容'] ?? '—' }}</td>
            <td>{{ record['状态'] ?? '—' }}</td>
          </tr>
          <tr v-if="!maintenanceRecords.length">
            <td colspan="4" class="empty-state">暂无维修记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条特种车辆记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null | string[]>

const ENDPOINT = '/api/vehicle'
const columns = ["车辆编号", "车辆类型", "所属车队", "车辆状态", "年检日期", "车辆年限", "驾驶员", "燃油量", "调度状态", "不可调度原因"]
const filterFields = ["车辆编号", "车辆类型", "所属车队"]

const stats = ref([
  { label: '可用车辆', value: 0 },
  { label: '待命车辆', value: 0 },
  { label: '出勤车辆', value: 0 },
  { label: '维修车辆', value: 0 },
  { label: '报废车辆', value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const filters = ref<Record<string, string>>({})
const dispatchRecords = ref<Row[]>([])
const maintenanceRecords = ref<Row[]>([])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function exportDispatch() {
  window.open(`${ENDPOINT}/export-dispatch`, '_blank')
}

function openCreate() {
  errorMessage.value = '特种车辆登记入口尚未接入审批流'
}

function actionsFor(row: Row): string[] {
  const status = String(row['status'] ?? '')
  if (status === '待命') return ['调度出勤', '补油', '登记维修', '申请报废']
  if (status === '出勤中') return ['收车']
  if (status === '维修中') return ['修竣']
  return []
}

function dispatchTagClass(status: string): string {
  if (status === '可调度') return 'tag-ok'
  if (status === '需补油') return 'tag-warn'
  if (status === '已出勤' || status === '维修中') return 'tag-info'
  if (status === '已报废' || status === '不可调度') return 'tag-ban'
  return ''
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '特种车辆动作未生效，请稍后重试'
    } else {
      infoMessage.value = payload.message || ''
    }
    await reload()
    await loadRecords()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '特种车辆操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    stats.value = [
      { label: '可用车辆', value: payload['可用车辆'] ?? 0 },
      { label: '待命车辆', value: payload['待命车辆'] ?? 0 },
      { label: '出勤车辆', value: payload['出勤车辆'] ?? 0 },
      { label: '维修车辆', value: payload['维修车辆'] ?? 0 },
      { label: '报废车辆', value: payload['报废车辆'] ?? 0 },
    ]
  } catch {
    // 统计读取失败时保留默认值，不阻塞列表
  }
}

async function loadRecords() {
  try {
    const [dispatchRes, maintenanceRes] = await Promise.all([
      request(`${ENDPOINT}/dispatch-records`),
      request(`${ENDPOINT}/maintenance-records`),
    ])
    if (dispatchRes.ok) {
      const payload = await dispatchRes.json()
      dispatchRecords.value = payload.items ?? []
    }
    if (maintenanceRes.ok) {
      const payload = await maintenanceRes.json()
      maintenanceRecords.value = payload.items ?? []
    }
  } catch {
    // 记录读取失败时保留空列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('特种车辆列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '特种车辆列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
  void loadRecords()
})
</script>

<style scoped>
.stat-available {
  color: #1a7f37;
}

.dispatch-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.tag-ok {
  background: #e6f4ea;
  color: #1a7f37;
}

.tag-warn {
  background: #fff4e5;
  color: #b25e09;
}

.tag-info {
  background: #e8f0fe;
  color: #1a4fb2;
}

.tag-ban {
  background: #fdecea;
  color: #b3261e;
}

.reason-text {
  color: #b3261e;
  font-size: 12px;
}

.record-section {
  margin-top: 24px;
}

.record-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.record-head h3 {
  margin: 0;
  font-size: 15px;
}

.record-count {
  color: #6b7280;
  font-size: 12px;
}

.info-text {
  color: #1a7f37;
}

.error-text {
  color: #b3261e;
}
</style>
