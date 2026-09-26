const $ = (id) => document.getElementById(id);
const money = (value) => value == null ? "—" : `¥${Number(value).toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const integer = (value) => Number(value || 0).toLocaleString("zh-CN");
const api = async (path) => {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
};

async function loadCatalog() {
  const health = await api("/api/health");
  const quality = await api("/api/data_quality");
  const stores = await api("/api/stores").catch(() => null);
  if (stores?.stores) {
    for (const store of stores.stores) {
      const option = document.createElement("option");
      option.value = store.store_id;
      option.textContent = `${store.store_id} ${store.store_name}`;
      $("store").appendChild(option);
    }
  }
  const policy = quality.metric_policy || {};
  $("policy").textContent = `指标口径：${policy.doc_id || "未知"} ${policy.title || ""} · 索引文档 ${health.kb_docs} 份`;
  renderQuality(quality);
}

function renderCards(data) {
  const items = [["净营业额", money(data.net_revenue)], ["退款金额", money(data.refund_amount)], ["有效订单", integer(data.orders)], ["客单价", money(data.aov)], ["销量", integer(data.qty)]];
  $("cards").innerHTML = items.map(([label, value]) => `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`).join("");
}

function renderChart(days) {
  const max = Math.max(...days.map((d) => Number(d.net_revenue) || 0), 1);
  $("chart").innerHTML = days.map((day) => {
    const value = Number(day.net_revenue) || 0;
    const height = Math.max(2, value / max * 205);
    return `<div class="bar-col" title="${day.date}: ${money(value)}"><div class="bar-value">${value ? Math.round(value).toLocaleString("zh-CN") : "0"}</div><div class="bar" style="height:${height}px"></div><div class="bar-label">${day.date.slice(5)}</div></div>`;
  }).join("");
}

function renderProducts(items) {
  $("products").innerHTML = items.map((item) => `<tr><td>${item.product_name || item.product_id}</td><td>${money(item.net_revenue)}</td><td>${integer(item.orders)}</td><td>${integer(item.qty)}</td></tr>`).join("") || `<tr><td colspan="4">没有数据</td></tr>`;
}

function renderQuality(data) {
  const report = data.cleaning_report || {};
  const removed = report.removed || {};
  const entries = [["原始行数", report.raw_rows], ["保留行数", report.kept_rows], ["坏日期", removed["1_unparseable_date"] || 0], ["空/坏金额", removed["2_empty_amount"] || 0], ["数量无效", removed["3_qty_le_zero"] || 0], ["门店外键", removed["4_store_not_in_stores"] || 0], ["商品外键", removed["5_product_not_in_products"] || 0], ["重复行", removed["6_duplicate_row"] || 0]];
  $("quality-grid").innerHTML = entries.map(([label, value]) => `<div class="quality-item"><small>${label}</small><strong>${integer(value)}</strong></div>`).join("");
  $("cleaned-at").textContent = data.cleaned_at ? `清洗时间 ${new Date(data.cleaned_at).toLocaleString("zh-CN")}` : "";
}

async function refresh() {
  const start = $("start").value, end = $("end").value, store = $("store").value;
  if (!start || !end || start > end) { $("status").textContent = "请选择有效日期区间"; return; }
  $("status").textContent = "加载中…";
  const suffix = store ? `&store_id=${encodeURIComponent(store)}` : "";
  try {
    const [summary, daily, products] = await Promise.all([
      api(`/api/metrics/summary?start=${start}&end=${end}${suffix}`),
      api(`/api/metrics/daily?start=${start}&end=${end}${suffix}`),
      api(`/api/metrics/top-products?start=${start}&end=${end}${suffix}`),
    ]);
    renderCards(summary); renderChart(daily.days); renderProducts(products.products);
    $("range-label").textContent = `${start} 至 ${end}`;
    $("status").textContent = `已更新 ${new Date().toLocaleTimeString("zh-CN")}`;
  } catch (error) { $("status").textContent = `加载失败：${error.message}`; }
}

$("refresh").addEventListener("click", refresh);
loadCatalog().then(refresh).catch((error) => { $("status").textContent = `初始化失败：${error.message}`; });
