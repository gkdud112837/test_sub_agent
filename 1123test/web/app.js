// 로컬 웹 화면. 구성은 /api/config, 진행 상황은 /api/state를 1초마다 읽는다.
const $ = (s) => document.querySelector(s);
const STATUS = { waiting: "대기", running: "실행 중", done: "완료", failed: "실패" };

let cfg = null;
let since = 0;
let currentRun = null;
let wasRunning = false;
let tab = "report";

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
  return body;
}

function el(tag, attrs = {}, text) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}

// ---------------------------------------------------------------- 보드

function buildBoard() {
  const board = $("#board");
  board.textContent = "";
  for (const ph of cfg.phases) {
    const col = el("div", { class: "phase" + (ph.parallel ? " par" : "") });
    const h = el("h3");
    h.append(el("span", {}, `${ph.id} · ${ph.label}`));
    if (ph.parallel) h.append(el("span", {}, `×${ph.agents.length} 병렬`));
    col.append(h);
    for (const name of ph.agents) {
      const key = name === "main" ? `main@${ph.id}` : name;
      const info = cfg.agents[name] || { label: "" };
      const card = el("div", { class: "agent waiting", "data-key": key, title: info.role || "" });
      card.append(el("div", { class: "nm" }, name === "main" ? info.label : name));
      card.append(el("div", { class: "lb" }, name === "main" ? info.role : info.label));
      const meta = el("div", { class: "meta" });
      meta.append(el("span", { class: "st" }, STATUS.waiting));
      card.append(meta);
      col.append(card);
    }
    board.append(col);
  }
}

function renderAgents(agents) {
  for (const card of document.querySelectorAll(".agent")) {
    const a = { ...(agents[card.dataset.key] || { status: "waiting", runs: 0, routes: [] }) };
    // 메인 세션이 P1 도중 처리한 R5는 P0(범위 정의) 카드에 표시한다
    if (card.dataset.key === "main@P0" && agents["main@P1"]) a.routes = [...(a.routes || []), ...agents["main@P1"].routes];
    card.className = `agent ${a.status}`;
    const meta = card.querySelector(".meta");
    meta.textContent = "";
    meta.append(el("span", { class: "st" }, STATUS[a.status] || a.status));
    if (a.runs > 1) meta.append(el("span", { class: "muted" }, `· ${a.runs}회`));
    for (const r of a.routes || []) meta.append(el("i", { class: "route" }, r));
    if (a.summary) card.title = a.summary;
  }
}

// ---------------------------------------------------------------- 상태 폴링

function addLog(events) {
  const log = $("#log");
  for (const e of events) {
    if (e.type !== "log") continue;
    const cls = /↩/.test(e.msg) ? "r" : /\] P\d/.test(e.msg) ? "p" : "";
    log.append(el("li", cls ? { class: cls } : {}, e.msg));
  }
  log.scrollTop = log.scrollHeight;
}

function setStatus(s) {
  const st = $("#status");
  st.className = "status";
  if (s.running) {
    st.textContent = `실행 중 · ${s.run_id} · ${s.mode}`;
  } else if (s.error) {
    st.textContent = `중단 · ${s.run_id} · ${s.error}`;
    st.classList.add("err");
  } else if (s.final) {
    st.textContent = `완료 · ${s.run_id} · ${s.final}`;
    st.classList.add("ok");
  } else {
    st.textContent = "대기 · 실행 버튼을 누르면 시작합니다.";
  }
  $("#runBtn").disabled = s.running;
}

async function poll() {
  try {
    const s = await api(`/api/state?since=${since}`);
    if (s.run_id && s.run_id !== currentRun) {
      currentRun = s.run_id;
      $("#log").textContent = "";
      since = 0;
      return setTimeout(poll, 0);
    }
    addLog(s.events);
    since = s.n_events;
    renderAgents(s.agents);
    setStatus(s);
    if (wasRunning && !s.running) await refreshRuns(s.run_id);
    wasRunning = s.running;
    setTimeout(poll, s.running ? 1000 : 3000);
  } catch (err) {
    $("#status").textContent = `서버 연결 끊김: ${err.message}`;
    $("#status").className = "status err";
    setTimeout(poll, 3000);
  }
}

async function startRun() {
  $("#runBtn").disabled = true;
  try {
    const r = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dry_run: $("#dry").checked, use_search: $("#search").checked }),
    });
    renderAgents({});
    wasRunning = true;
    await refreshRuns(r.run_id);
  } catch (err) {
    $("#status").textContent = `실행 못 함: ${err.message}`;
    $("#status").className = "status err";
    $("#runBtn").disabled = false;
  }
}

// ---------------------------------------------------------------- 결과 패널

async function refreshRuns(select) {
  const { runs } = await api("/api/runs");
  const sel = $("#runSel");
  sel.textContent = "";
  if (!runs.length) sel.append(el("option", { value: "" }, "실행 없음"));
  for (const r of runs) sel.append(el("option", { value: r }, r));
  if (select && runs.includes(select)) sel.value = select;
  await showTab(tab);
}

async function showTab(name) {
  tab = name;
  for (const b of document.querySelectorAll(".tabs button")) b.classList.toggle("on", b.dataset.tab === name);
  for (const v of ["report", "files", "runlog"]) $(`#view-${v}`).classList.toggle("hidden", v !== name);
  const run = $("#runSel").value;
  if (!run) return;
  if (name === "report") return loadReport(run);
  if (name === "files") return loadFiles(run);
  return loadRunlog(run);
}

async function loadReport(run) {
  const view = $("#view-report");
  try {
    const { html } = await api(`/api/report?run=${encodeURIComponent(run)}`);
    view.innerHTML = html; // 서버가 LLM 출력의 HTML 태그를 막은 뒤 변환한 결과
  } catch (err) {
    view.textContent = "";
    view.append(el("p", { class: "muted" }, err.message));
  }
}

async function loadFiles(run) {
  const { files } = await api(`/api/files?run=${encodeURIComponent(run)}`);
  const list = $("#fileList");
  list.textContent = "";
  let lastDir = null;
  for (const f of files) {
    const dir = f.path.includes("/") ? f.path.slice(0, f.path.lastIndexOf("/")) : ".";
    if (dir !== lastDir) {
      list.append(el("li", { class: "dir" }, dir + "/"));
      lastDir = dir;
    }
    const li = el("li", { "data-path": f.path }, f.path.slice(dir === "." ? 0 : dir.length + 1));
    li.addEventListener("click", () => openFile(run, f.path, li));
    list.append(li);
  }
}

async function openFile(run, path, li) {
  for (const n of document.querySelectorAll(".files li.on")) n.classList.remove("on");
  li.classList.add("on");
  const viewer = $("#viewer");
  viewer.textContent = "";
  const url = `/api/file?run=${encodeURIComponent(run)}&path=${encodeURIComponent(path)}`;
  if (path.endsWith(".png")) {
    viewer.append(el("img", { src: url, alt: path }));
    return;
  }
  const r = await fetch(url);
  viewer.append(el("pre", {}, await r.text()));
}

async function loadRunlog(run) {
  const view = $("#view-runlog");
  view.textContent = "";
  const r = await fetch(`/api/file?run=${encodeURIComponent(run)}&path=run_log.json`);
  if (!r.ok) return view.append(el("p", { class: "muted" }, "기록이 없습니다."));
  const data = JSON.parse(await r.text());
  const table = el("table");
  const head = el("tr");
  for (const h of ["id", "페이즈", "에이전트", "경로", "상태", "다시 돈 기록", "요약"]) head.append(el("th", {}, h));
  table.append(head);
  for (const e of data.entries) {
    const tr = el("tr");
    for (const v of [e.id, e.phase, e.agent, e.route || "", e.status, e.rerun_of ?? "", e.log_summary || ""]) {
      tr.append(el("td", {}, String(v)));
    }
    table.append(tr);
  }
  view.append(table);
}

// ---------------------------------------------------------------- 시작

async function init() {
  cfg = await api("/api/config");
  $("#model").textContent = `모델 ${cfg.model}`;
  const key = $("#key");
  key.textContent = cfg.api_key_ready ? "API 키 있음" : "API 키 없음 · dry-run만 가능";
  key.classList.toggle("warn", !cfg.api_key_ready);
  $("#dry").checked = !cfg.api_key_ready;
  $("#dry").disabled = !cfg.api_key_ready;
  $("#search").checked = cfg.use_search;
  buildBoard();
  $("#runBtn").addEventListener("click", startRun);
  $("#runSel").addEventListener("change", () => showTab(tab));
  for (const b of document.querySelectorAll(".tabs button")) b.addEventListener("click", () => showTab(b.dataset.tab));
  await refreshRuns();
  poll();
}

init().catch((err) => {
  $("#status").textContent = `화면을 불러오지 못했습니다: ${err.message}`;
  $("#status").className = "status err";
});
