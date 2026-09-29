<template>
  <section class="page" data-module="vehicle">
    <header class="page-head">
      <div>
        <h2>特种车辆调度</h2>
        <p class="page-desc">
          按年检日期、车辆年限与燃油量判定出勤口径：年检到期前 15 天内或已超期、车龄超限、燃油低于下限的车辆不允许调度出勤；已报废车辆不参与排班。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记特种车辆</button>
        <button class="btn" type="button" @click="exportLedger">导出车辆台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p v-if="notice.message" class="notice" :class="{ 'notice-error': notice.isError }">{{ notice.message }}</p>

    <form v-if="showCreate" class="create-panel" @submit.prevent="submitCreate">
      <label class="filter-item">
        <span>车辆编号 *</span>
        <input v-model="createForm.车辆编号" placeholder="如 VEHI-0011" />
      </label>
      <label class="filter-item">
        <span>车辆类型 *</span>
        <select v-model="createForm.车辆类型">
          <option v-for="type in vehicleTypes" :key="type" :value="type">{{ type }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>所属车队 *</span>
        <input v-model="createForm.所属车队" placeholder="如 机坪一队" />
      </label>
      <label class="filter-item">
        <span>驾驶员</span>
        <input v-model="createForm.驾驶员" />
      </label>
      <label class="filter-item">
        <span>年检日期</span>
        <input v-model="createForm.年检日期" type="date" />
      </label>
      <label class="filter-item">
        <span>投入使用日期</span>
        <input v-model="createForm.投入使用日期" type="date" />
      </label>
      <label class="filter-item">
        <span>燃油量(%)</span>
        <input v-model="createForm.燃油量" type="number" min="0" max="100" />
      </label>
      <button class="btn primary" type="submit">提交登记</button>
    </form>

    <h3 class="section-title">车辆台账</h3>
    <form class="filter-bar" @submit.prevent="reloadLedger">
      <label class="filter-item">
        <span>车辆编号</span>
        <input v-model="keyword" placeholder="按车辆编号检索" />
      </label>
      <label class="filter-item">
        <span>车辆状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>车辆编号</th>
          <th>车辆类型</th>
          <th>所属车队</th>
          <th>驾驶员</th>
          <th>年检日期</th>
          <th>车龄(年)</th>
          <th>燃油量</th>
          <th>状态</th>
          <th>出勤判定</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['车辆编号'] ?? '—' }}</td>
          <td>{{ row['车辆类型'] ?? '—' }}</td>
          <td>{{ row['所属车队'] ?? '—' }}</td>
          <td>{{ row['驾驶员'] ?? '—' }}</td>
          <td>{{ row['年检日期'] ?? '—' }}</td>
          <td>{{ row['车龄'] ?? '—' }}</td>
          <td>{{ withUnit(row['燃油量'], '%') }}</td>
          <td>{{ row.status ?? '—' }}</td>
          <td :class="row['可出勤'] ? 'ok-text' : 'bad-text'">{{ row['出勤判定'] ?? '—' }}</td>
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
            <span v-if="!actionsFor(row).length" class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="10" class="empty-state">暂无特种车辆数据，可先登记特种车辆</td>
        </tr>
      </tbody>
    </table>
    <footer class="page-foot">
      <span>共 {{ total }} 条特种车辆记录</span>
    </footer>

    <div class="section-head">
      <h3 class="section-title">当日出勤清单</h3>
      <div class="section-actions">
        <input v-model="dispatchDate" type="date" @change="reloadDispatch" />
        <button class="btn" type="button" @click="exportDispatch">导出当日出勤单</button>
      </div>
    </div>
    <p class="section-desc">
      {{ dispatchDate }} 出车 {{ dispatchTotal }} 单 · 当前可用车辆 {{ summary.available }} 辆（与车辆台账、运营概览同一口径）
    </p>
    <table class="data-table">
      <thead>
        <tr>
          <th>单号</th>
          <th>车辆编号</th>
          <th>车辆类型</th>
          <th>驾驶员</th>
          <th>出勤时间</th>
          <th>收车时间</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="record in dispatchRows" :key="String(record.id)">
          <td>{{ record['单号'] ?? '—' }}</td>
          <td>{{ record['车辆编号'] ?? '—' }}</td>
          <td>{{ record['车辆类型'] ?? '—' }}</td>
          <td>{{ record['驾驶员'] ?? '—' }}</td>
          <td>{{ record['出勤时间'] ?? '—' }}</td>
          <td>{{ record['收车时间'] ?? '—' }}</td>
          <td>{{ record['状态'] ?? '—' }}</td>
        </tr>
        <tr v-if="!dispatchRows.length">
          <td colspan="7" class="empty-state">当日暂无出勤记录</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">车型判定阈值</h3>
    <p class="section-desc">不同车型的出勤判定阈值分开设置；未列出的车型按默认口径执行。</p>
    <table class="data-table">
      <thead>
        <tr>
          <th>车型</th>
          <th>燃油下限(%)</th>
          <th>车龄上限(年)</th>
          <th>年检临期窗口(天)</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(threshold, type) in thresholdDrafts" :key="type">
          <td>{{ type }}</td>
          <td><input v-model.number="threshold.fuel_min" class="num-input" type="number" min="0" max="100" /></td>
          <td><input v-model.number="threshold.max_age_years" class="num-input" type="number" min="0" /></td>
          <td><input v-model.number="threshold.inspection_window_days" class="num-input" type="number" min="0" /></td>
          <td><button class="link" type="button" @click="saveThreshold(String(type))">保存</button></td>
        </tr>
        <tr>
          <td>默认口径（未列车型）</td>
          <td>{{ defaultThreshold.fuel_min }}</td>
          <td>{{ defaultThreshold.max_age_years }}</td>
          <td>{{ defaultThreshold.inspection_window_days }}</td>
          <td class="muted-text">内置</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">维修记录</h3>
    <p class="section-desc">同一辆车的维修记录重复登记时只保留最近一次。</p>
    <table class="data-table">
      <thead>
        <tr>
          <th>车辆编号</th>
          <th>维修日期</th>
          <th>维修内容</th>
          <th>登记时间</th>
          <th>经办人</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="record in maintenanceRows" :key="String(record.id)">
          <td>{{ record['车辆编号'] ?? '—' }}</td>
          <td>{{ record['维修日期'] ?? '—' }}</td>
          <td>{{ record['维修内容'] ?? '—' }}</td>
          <td>{{ record['登记时间'] ?? '—' }}</td>
          <td>{{ record['经办人'] ?? '—' }}</td>
        </tr>
        <tr v-if="!maintenanceRows.length">
          <td colspan="5" class="empty-state">暂无维修记录</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type RecordRow = Record<string, string | number | null>
type Summary = { total: number; available: number; on_duty: number; maintenance: number; scrapped: number; blocked: number }
type Threshold = { fuel_min: number; max_age_years: number; inspection_window_days: number }
type ActionResult = { ok: boolean; message: string }

const ENDPOINT = '/api/vehicle'
const statuses = ['待命', '出勤中', '维修中', '已报废']
const STATUS_ACTIONS: Record<string, string[]> = {
  待命: ['调度出勤', '补油', '登记维修', '申请报废'],
  出勤中: ['收车'],
  维修中: ['完成维修', '申请报废'],
  已报废: [],
}
const FALLBACK_TYPES = ['牵引车', '摆渡车', '加油车', '除冰车', '平台车', '食品车']

function localToday(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const summary = ref<Summary>({ total: 0, available: 0, on_duty: 0, maintenance: 0, scrapped: 0, blocked: 0 })
const dispatchRows = ref<RecordRow[]>([])
const dispatchTotal = ref(0)
const dispatchDate = ref(localToday())
const maintenanceRows = ref<RecordRow[]>([])
const thresholdDrafts = ref<Record<string, Threshold>>({})
const defaultThreshold = ref<Threshold>({ fuel_min: 20, max_age_years: 10, inspection_window_days: 15 })
const notice = reactive({ message: '', isError: false })
const showCreate = ref(false)
const createForm = reactive({
  车辆编号: '',
  车辆类型: '牵引车',
  所属车队: '',
  驾驶员: '',
  年检日期: '',
  投入使用日期: '',
  燃油量: '100',
})

const stats = computed(() => [
  { label: '可用车辆', value: summary.value.available },
  { label: '暂不可出勤', value: summary.value.blocked },
  { label: '出勤中', value: summary.value.on_duty },
  { label: '维修中', value: summary.value.maintenance },
  { label: '已报废', value: summary.value.scrapped },
])

const vehicleTypes = computed(() => {
  const types = Object.keys(thresholdDrafts.value)
  return types.length ? types : FALLBACK_TYPES
})

function withUnit(value: string | number | boolean | null | undefined, unit: string): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return `${value}${unit}`
}

function actionsFor(row: Row): string[] {
  return STATUS_ACTIONS[String(row.status)] ?? []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reloadLedger()
}

function exportLedger() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function exportDispatch() {
  window.open(`${ENDPOINT}/dispatch/export?day=${dispatchDate.value}`, '_blank')
}

async function callAction(path: string, values: Record<string, unknown>): Promise<boolean> {
  const response = await request(path, { method: 'POST', body: JSON.stringify({ values }) })
  const payload = (await response.json()) as ActionResult
  notice.message = payload.message
  notice.isError = !payload.ok
  return payload.ok
}

async function runAction(action: string, row: Row) {
  notice.message = ''
  const values: Record<string, unknown> = { action }
  if (action === '登记维修') {
    const content = window.prompt('填写维修内容', '例行检修')
    if (content === null) {
      return
    }
    values['维修内容'] = content
  }
  try {
    await callAction(`${ENDPOINT}/${String(row.id)}/actions`, values)
    await reloadAll()
  } catch (error) {
    notice.message = error instanceof Error ? error.message : '特种车辆操作失败'
    notice.isError = true
  }
}

async function submitCreate() {
  notice.message = ''
  try {
    const ok = await callAction(ENDPOINT, { ...createForm })
    if (ok) {
      showCreate.value = false
      createForm.车辆编号 = ''
      createForm.所属车队 = ''
      createForm.驾驶员 = ''
      createForm.年检日期 = ''
      createForm.投入使用日期 = ''
      createForm.燃油量 = '100'
      await reloadAll()
    }
  } catch (error) {
    notice.message = error instanceof Error ? error.message : '特种车辆登记失败'
    notice.isError = true
  }
}

async function saveThreshold(type: string) {
  notice.message = ''
  const draft = thresholdDrafts.value[type]
  if (!draft) {
    return
  }
  try {
    const response = await request(`${ENDPOINT}/thresholds/${encodeURIComponent(type)}`, {
      method: 'PUT',
      body: JSON.stringify({ values: draft }),
    })
    const payload = (await response.json()) as ActionResult
    notice.message = payload.message
    notice.isError = !payload.ok
    if (payload.ok) {
      await reloadAll()
    }
  } catch (error) {
    notice.message = error instanceof Error ? error.message : '阈值保存失败'
    notice.isError = true
  }
}

async function reloadLedger() {
  const query = new URLSearchParams()
  if (keyword.value) {
    query.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  const response = await request(`${ENDPOINT}?${query.toString()}`)
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function reloadSummary() {
  const response = await request(`${ENDPOINT}/summary`)
  summary.value = (await response.json()) as Summary
}

async function reloadDispatch() {
  const response = await request(`${ENDPOINT}/dispatch?day=${dispatchDate.value}`)
  const payload = await response.json()
  dispatchRows.value = payload.items ?? []
  dispatchTotal.value = payload.total ?? dispatchRows.value.length
}

async function reloadMaintenance() {
  const response = await request(`${ENDPOINT}/maintenance`)
  const payload = await response.json()
  maintenanceRows.value = payload.items ?? []
}

async function reloadThresholds() {
  const response = await request(`${ENDPOINT}/thresholds`)
  const payload = await response.json()
  defaultThreshold.value = payload.default ?? defaultThreshold.value
  const drafts: Record<string, Threshold> = {}
  for (const [type, value] of Object.entries(payload.types ?? {})) {
    drafts[type] = { ...(value as Threshold) }
  }
  thresholdDrafts.value = drafts
}

async function reloadAll() {
  await Promise.all([reloadLedger(), reloadSummary(), reloadDispatch(), reloadMaintenance(), reloadThresholds()])
}

onMounted(async () => {
  try {
    await reloadAll()
  } catch (error) {
    notice.message = error instanceof Error ? error.message : '特种车辆数据读取失败'
    notice.isError = true
  }
})
</script>

<style scoped>
.notice {
  margin: 8px 0;
  padding: 8px 12px;
  border: 1px solid #b7d3f8;
  border-radius: 6px;
  background: #eef4fe;
  color: #1d4fa1;
  font-size: 13px;
}

.notice-error {
  border-color: #f3c2c2;
  background: #fdf0f0;
  color: #b42318;
}

.section-title {
  margin: 20px 0 8px;
  font-size: 15px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
}

.section-head .section-title {
  margin: 0;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.section-desc {
  margin: 6px 0 8px;
  color: var(--muted, #64748b);
  font-size: 12px;
}

.create-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px dashed var(--border, #d8dee6);
  border-radius: 8px;
  background: #fff;
}

.ok-text {
  color: #15803d;
}

.bad-text {
  color: #b42318;
}

.muted-text {
  color: var(--muted, #64748b);
}

.num-input {
  width: 72px;
}
</style>
