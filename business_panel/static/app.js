const totalsEl = document.querySelector("#totals");
const cardsEl = document.querySelector("#cards");
const feedbackEl = document.querySelector("#feedback");
const pollIntervalMs = Number(document.body.dataset.refreshMs || "15000");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setFeedback(message) {
  if (!feedbackEl) {
    return;
  }
  feedbackEl.hidden = !message;
  feedbackEl.textContent = message || "";
}

function extractMessage(payload, fallback) {
  if (payload && typeof payload === "object") {
    if (payload.error) {
      return payload.error;
    }
    if (payload.stderr) {
      return payload.stderr;
    }
    if (payload.stdout) {
      return payload.stdout;
    }
  }
  return fallback;
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw new Error(extractMessage(payload, `请求失败 (${response.status})`));
  }

  return payload;
}

function renderTotals(payload) {
  const items = [
    ["total", "业务总数"],
    ["healthy", "正常"],
    ["degraded", "部分异常"],
    ["failed", "异常"],
    ["not_installed", "未安装"],
  ];
  totalsEl.innerHTML = items
    .map(
      ([key, label]) => `
        <article class="card metric">
          <strong>${payload.totals[key]}</strong>
          <span>${label}</span>
        </article>
      `
    )
    .join("");
}

function renderCards(units) {
  cardsEl.innerHTML = units
    .map(
      (unit) => `
        <article class="card">
          <div class="card-top">
            <div>
              <h2>${escapeHtml(unit.display_name)}</h2>
              <p>${escapeHtml(unit.description)}</p>
            </div>
            <span class="status-badge status-${escapeHtml(unit.overall_state)}">${escapeHtml(unit.overall_state)}</span>
          </div>
          <p>${escapeHtml(unit.failure_summary)}</p>
          <ul class="details">
            <li>容器：${escapeHtml(unit.container.summary)}</li>
            <li>入口：${escapeHtml(unit.endpoint.summary)}</li>
            <li>认证：${escapeHtml(unit.auth.summary)}</li>
          </ul>
          <div class="actions">
            <a class="link-button" href="${escapeHtml(unit.open_url || unit.entry_url)}" target="_blank" rel="noreferrer">打开</a>
            ${unit.available_actions
              .map(
                (action) =>
                  `<button data-unit="${escapeHtml(unit.unit_id)}" data-action="${escapeHtml(action)}">${escapeHtml(action)}</button>`
              )
              .join("")}
          </div>
        </article>
      `
    )
    .join("");
}

async function loadStatus() {
  try {
    const payload = await requestJson("/api/status");
    renderTotals(payload);
    renderCards(payload.units);
    setFeedback("");
    return payload;
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : "状态刷新失败");
    return null;
  }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const { unit, action } = button.dataset;
  if (!window.confirm(`确认执行 ${unit} / ${action} ?`)) {
    return;
  }
  button.disabled = true;
  try {
    const payload = await requestJson("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ unit_id: unit, action }),
    });
    if (!payload || payload.ok === false) {
      throw new Error(extractMessage(payload, "控制操作失败"));
    }
    await loadStatus();
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : "控制操作失败");
  } finally {
    button.disabled = false;
  }
});

void loadStatus();
window.setInterval(() => {
  void loadStatus();
}, pollIntervalMs);
