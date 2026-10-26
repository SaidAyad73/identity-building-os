/* Identity Building OS — Extendable Frontend Client */

const state = {
  view: "dashboard",
  scope: "week",
  selectedDate: "",
  twoMinuteMode: false,
  captureKind: "vote",
  selectedCaptureIdentities: new Set(),
  modalHabitIdentities: new Set(),
  feedFilter: "all",
  data: null,
  guidanceDocs: [],
  activeGuidanceId: null,
  editingGuidance: false,
};

function isDarkMode() {
  const rootTheme = document.documentElement.getAttribute("data-theme");
  if (rootTheme === "dark") return true;
  if (rootTheme === "light") return false;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function identColor(ident) {
  if (!ident) return "#2a78d6";
  return isDarkMode() ? (ident.color_dark || ident.color_light) : (ident.color_light || "#2a78d6");
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(msg) {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

async function loadState() {
  const params = new URLSearchParams({ scope: state.scope });
  if (state.selectedDate) {
    params.set("date", state.selectedDate);
  }
  const data = await api(`/api/state?${params.toString()}`);
  state.data = data;
  state.selectedDate = data.selected_date;

  const validIds = new Set(data.identities.map((i) => i.id));
  for (const id of Array.from(state.selectedCaptureIdentities)) {
    if (!validIds.has(id)) state.selectedCaptureIdentities.delete(id);
  }
  if (state.selectedCaptureIdentities.size === 0 && data.identities.length > 0) {
    state.selectedCaptureIdentities.add(data.identities[0].id);
  }

  renderAll();
}

async function loadGuidance() {
  const res = await api("/api/guidance");
  state.guidanceDocs = res.documents || [];
  if (!state.activeGuidanceId && state.guidanceDocs.length > 0) {
    state.activeGuidanceId = state.guidanceDocs[0].id;
  }
  renderGuidanceView();
}

function renderAll() {
  if (!state.data) return;
  renderToolbarAndBanner();
  renderQuickCapture();
  renderDonutChart();
  renderCalendar();
  renderIdentityCards();
  renderGuardrailsAndFeed();
  renderWeeklyReview();
  renderManageView();
}

function renderToolbarAndBanner() {
  const { selected_date, week_start, week_end, weekly_review } = state.data;
  document.getElementById("selectedDateInput").value = selected_date;
  document.getElementById("weekRangeLabel").textContent = `Week: ${week_start} → ${week_end}`;

  document.querySelectorAll(".scope-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.scope === state.scope);
  });

  const pinned = weekly_review?.pinned_adjustment || {};
  const bannerText =
    pinned.one_adjustment ||
    pinned.next_smallest_action ||
    "Review weekly, not obsessively every day. Choose 1 system adjustment in your Weekly Review.";
  document.getElementById("pinnedAdjustmentText").textContent = bannerText;
}

function renderQuickCapture() {
  const wrap = document.getElementById("captureIdentityPills");
  wrap.innerHTML = "";
  for (const ident of state.data.identities) {
    const btn = document.createElement("button");
    btn.type = "button";
    const selected = state.selectedCaptureIdentities.has(ident.id);
    btn.className = `identity-pill ${selected ? "selected" : ""}`;
    btn.innerHTML = `<span class="swatch" style="background:${identColor(ident)}"></span><span>${escapeHtml(ident.name)}</span>`;
    btn.addEventListener("click", () => {
      if (state.selectedCaptureIdentities.has(ident.id)) {
        if (state.selectedCaptureIdentities.size > 1) {
          state.selectedCaptureIdentities.delete(ident.id);
        }
      } else {
        state.selectedCaptureIdentities.add(ident.id);
      }
      renderQuickCapture();
    });
    wrap.appendChild(btn);
  }
}

/* -------------------------------------------------------------------------- */
/* SVG Donut Chart with 2px Surface Gap & Fractional Attribution              */
/* -------------------------------------------------------------------------- */
function polarToCartesian(cx, cy, r, angleInDegrees) {
  const rad = ((angleInDegrees - 90) * Math.PI) / 180.0;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

function describeArcSlice(cx, cy, rOuter, rInner, startAngle, endAngle) {
  const spread = Math.min(endAngle - startAngle, 359.99);
  const end = startAngle + spread;
  const startOuter = polarToCartesian(cx, cy, rOuter, end);
  const endOuter = polarToCartesian(cx, cy, rOuter, startAngle);
  const startInner = polarToCartesian(cx, cy, rInner, end);
  const endInner = polarToCartesian(cx, cy, rInner, startAngle);
  const largeArc = spread > 180 ? 1 : 0;

  return [
    "M", startOuter.x, startOuter.y,
    "A", rOuter, rOuter, 0, largeArc, 0, endOuter.x, endOuter.y,
    "L", endInner.x, endInner.y,
    "A", rInner, rInner, 0, largeArc, 1, startInner.x, startInner.y,
    "Z",
  ].join(" ");
}

function renderDonutChart() {
  const svg = document.getElementById("identityDonutSvg");
  const tooltip = document.getElementById("chartTooltip");
  const tbody = document.getElementById("chartLegendBody");
  const { chart } = state.data;

  svg.innerHTML = "";
  tbody.innerHTML = "";

  const cx = 120;
  const cy = 120;
  const rOuter = 98;
  const rInner = 62;

  const activeSlices = chart.slices.filter((s) => s.exact_weight > 0);
  const totalPositiveWeight = activeSlices.reduce((acc, s) => acc + s.exact_weight, 0);

  if (totalPositiveWeight <= 0 || activeSlices.length === 0) {
    const emptyCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    emptyCircle.setAttribute("cx", cx);
    emptyCircle.setAttribute("cy", cy);
    emptyCircle.setAttribute("r", (rOuter + rInner) / 2);
    emptyCircle.setAttribute("fill", "none");
    emptyCircle.setAttribute("stroke", "var(--border-subtle)");
    emptyCircle.setAttribute("stroke-width", rOuter - rInner);
    svg.appendChild(emptyCircle);
  } else {
    let currentAngle = 0;
    for (const slice of activeSlices) {
      const sweep = (slice.exact_weight / totalPositiveWeight) * 360;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", describeArcSlice(cx, cy, rOuter, rInner, currentAngle, currentAngle + sweep));
      path.setAttribute("fill", isDarkMode() ? slice.color_dark : slice.color_light);
      path.setAttribute("stroke", "var(--surface-1)");
      path.setAttribute("stroke-width", "2");
      path.setAttribute("class", "donut-slice");

      path.addEventListener("mouseenter", () => {
        tooltip.hidden = false;
        tooltip.innerHTML = `<strong>${escapeHtml(slice.name)}</strong>: ${slice.weighted_votes} net votes (${slice.percentage}%) • ${slice.raw_touches} votes${slice.devote_count ? ` / ${slice.devote_count} devotes` : ""}`;
      });
      path.addEventListener("mouseleave", () => {
        tooltip.hidden = true;
      });

      svg.appendChild(path);
      currentAngle += sweep;
    }
  }

  const centerNum = document.createElementNS("http://www.w3.org/2000/svg", "text");
  centerNum.setAttribute("x", cx);
  centerNum.setAttribute("y", cy - 4);
  centerNum.setAttribute("text-anchor", "middle");
  centerNum.setAttribute("fill", "var(--text-primary)");
  centerNum.setAttribute("font-size", "26");
  centerNum.setAttribute("font-weight", "700");
  centerNum.textContent = chart.total_votes;
  svg.appendChild(centerNum);

  const centerSub = document.createElementNS("http://www.w3.org/2000/svg", "text");
  centerSub.setAttribute("x", cx);
  centerSub.setAttribute("y", cy + 18);
  centerSub.setAttribute("text-anchor", "middle");
  centerSub.setAttribute("fill", "var(--text-secondary)");
  centerSub.setAttribute("font-size", "11");
  centerSub.textContent = state.scope === "day" ? "Net Votes (Day)" : "Net Votes (Week)";
  svg.appendChild(centerSub);

  for (const slice of chart.slices) {
    const color = isDarkMode() ? slice.color_dark : slice.color_light;
    const tr = document.createElement("tr");
    const actionSummary = slice.devote_count
      ? `${slice.raw_touches}v / -${slice.devote_count}d`
      : `${slice.raw_touches}`;
    tr.innerHTML = `
      <td>
        <div class="legend-ident-cell">
          <span class="legend-swatch" style="background:${color}"></span>
          <span>${escapeHtml(slice.name)}</span>
        </div>
      </td>
      <td class="num">${slice.weighted_votes}</td>
      <td class="num">${slice.percentage}%</td>
      <td class="num">${actionSummary}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById("kpiTotalVotes").textContent = chart.total_votes;
  document.getElementById("kpiTwoMinCount").textContent = chart.two_minute_votes;
  document.getElementById("kpiActiveIdents").textContent = `${chart.active_identities_count}/${chart.slices.length}`;
}

/* -------------------------------------------------------------------------- */
/* Calendar Strip & 28-Day Heatmap                                            */
/* -------------------------------------------------------------------------- */
function renderCalendar() {
  const strip = document.getElementById("weekDaysStrip");
  const heatmap = document.getElementById("heatmapGrid");
  const { calendar, identities } = state.data;
  const identMap = Object.fromEntries(identities.map((i) => [i.id, i]));

  strip.innerHTML = "";
  for (const day of calendar.week_days) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = `day-tile ${day.is_selected ? "selected" : ""} ${day.is_today ? "today" : ""}`;
    const dotsHtml = day.identities_touched
      .map((iid) => {
        const ident = identMap[iid];
        return ident ? `<span class="day-dot" style="background:${identColor(ident)}"></span>` : "";
      })
      .join("");
    const recoveryMark = day.never_miss_twice_recovered ? `<span title="Never Miss Twice recovery!">↺</span> ` : "";
    tile.innerHTML = `
      <span class="day-name">${day.day_name}</span>
      <span class="day-num">${day.day_num}</span>
      <div class="day-dots">${dotsHtml}</div>
      <span class="day-meta">${recoveryMark}${day.vote_count}v${day.devote_count ? ` · -${day.devote_count}d` : ""}${day.obstacle_count ? ` · ${day.obstacle_count}!` : ""}</span>
    `;
    tile.addEventListener("click", () => {
      state.selectedDate = day.date;
      loadState();
    });
    strip.appendChild(tile);
  }

  heatmap.innerHTML = "";
  for (const cell of calendar.heatmap_28d) {
    const el = document.createElement("button");
    el.type = "button";
    const lvl = cell.vote_count === 0 ? 0 : cell.vote_count === 1 ? 1 : cell.vote_count <= 3 ? 2 : 3;
    el.className = `heat-cell level-${lvl} ${cell.is_selected ? "selected" : ""}`;
    el.title = `${cell.date}: ${cell.vote_count} net votes`;
    el.textContent = cell.date.slice(8);
    el.addEventListener("click", () => {
      state.selectedDate = cell.date;
      loadState();
    });
    heatmap.appendChild(el);
  }
}

/* -------------------------------------------------------------------------- */
/* Extendable Identity Cards, 1-Click Vote, Devote & Delete                   */
/* -------------------------------------------------------------------------- */
function renderIdentityCards() {
  const grid = document.getElementById("identityCardsGrid");
  grid.innerHTML = "";
  const { identities, habits, settings } = state.data;
  const stages = (settings.stages || []).map((s) => s.name || s);

  for (const ident of identities) {
    const color = identColor(ident);
    const cardHabits = habits.filter(
      (h) => h.category === "identity_habit" && h.identity_ids.includes(ident.id)
    );

    const card = document.createElement("article");
    card.className = "identity-card";
    card.style.setProperty("--ident-color", color);

    const stageOptions = stages
      .map(
        (st) =>
          `<option value="${escapeHtml(st)}" ${st === ident.current_stage ? "selected" : ""}>${escapeHtml(st)}</option>`
      )
      .join("");

    const habitsHtml = cardHabits.length
      ? cardHabits
          .map((h) => {
            const displayTitle = state.twoMinuteMode && h.two_minute_version ? h.two_minute_version : h.title;
            const doneCount = h.completed_on_selected_date || 0;
            return `
              <div class="habit-item ${doneCount > 0 ? "completed-today" : ""}">
                <div class="habit-text-wrap">
                  <span class="habit-title-text">
                    <span class="habit-cadence-tag">${escapeHtml(h.cadence)}</span>
                    ${escapeHtml(displayTitle)}
                  </span>
                </div>
                <div class="habit-actions">
                  <button type="button" class="btn-vote-sm" data-quick-habit="${escapeHtml(h.id)}" data-ident="${escapeHtml(ident.id)}">
                    ${doneCount > 0 ? `✓ Voted (${doneCount})` : "+ Vote"}
                  </button>
                  <button type="button" class="btn-devote-sm" title="Devote (undo today's vote or subtract a vote in logs)" data-devote-habit="${escapeHtml(h.id)}" data-ident="${escapeHtml(ident.id)}">
                    − Devote
                  </button>
                  <button type="button" class="icon-btn-sm" title="Edit habit" data-edit-habit="${escapeHtml(h.id)}">✎</button>
                  <button type="button" class="icon-btn-sm" title="Delete habit" data-del-habit="${escapeHtml(h.id)}">✕</button>
                </div>
              </div>
            `;
          })
          .join("")
      : `<p class="card-subtitle">No habits linked yet. Click <strong>+ Habit</strong> below to add one.</p>`;

    const recentSnippet =
      ident.recent_actions && ident.recent_actions.length > 0
        ? `Latest: “${escapeHtml(ident.recent_actions[0].title)}” (${ident.recent_actions[0].timestamp_display || ident.recent_actions[0].created_at})`
        : "No votes in current view yet";

    card.innerHTML = `
      <div>
        <div class="ident-card-top">
          <div>
            <div class="ident-name-row">
              <span class="ident-color-dot"></span>
              <h3 class="ident-title">${escapeHtml(ident.name)}</h3>
            </div>
            <p class="ident-tagline">${escapeHtml(ident.tagline)}</p>
          </div>
          <div class="ident-stats-badges">
            <span class="vote-count-badge" title="Net weighted votes / Share">${ident.weighted_votes}v · ${ident.percentage}%</span>
            <select class="stage-select-inline" data-stage-ident="${escapeHtml(ident.id)}" aria-label="Maturity stage for ${escapeHtml(ident.name)}">
              ${stageOptions}
            </select>
          </div>
        </div>

        <div class="habit-list" style="margin-top:12px;">
          ${habitsHtml}
        </div>
      </div>

      <div class="ident-card-footer">
        <span>${recentSnippet}</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <button type="button" class="btn-link" data-add-habit-for="${escapeHtml(ident.id)}">+ Habit</button>
          <button type="button" class="btn-link" data-edit-ident="${escapeHtml(ident.id)}">Edit</button>
          <button type="button" class="btn-danger-link" data-del-ident="${escapeHtml(ident.id)}">Delete</button>
        </div>
      </div>
    `;

    grid.appendChild(card);
  }

  // Bind 1-click habit vote buttons
  grid.querySelectorAll("[data-quick-habit]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const habitId = btn.dataset.quickHabit;
      const habit = state.data.habits.find((h) => h.id === habitId);
      if (!habit) return;
      const useTwoMin = state.twoMinuteMode;
      const title = useTwoMin && habit.two_minute_version ? habit.two_minute_version : habit.title;
      const res = await api("/api/actions", {
        method: "POST",
        body: JSON.stringify({
          habit_id: habit.id,
          title,
          action_date: state.selectedDate,
          identity_ids: habit.identity_ids,
          used_two_minute_rule: useTwoMin,
          kind: "vote",
        }),
      });
      showToast(`Vote cast (${res.timestamp}): ${title}`);
      await loadState();
    });
  });

  // Bind 1-click habit devote buttons
  grid.querySelectorAll("[data-devote-habit]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const habitId = btn.dataset.devoteHabit;
      const habit = state.data.habits.find((h) => h.id === habitId);
      if (!habit) return;
      const res = await api("/api/actions/devote", {
        method: "POST",
        body: JSON.stringify({
          habit_id: habit.id,
          action_date: state.selectedDate,
          identity_ids: habit.identity_ids,
        }),
      });
      if (res.effect === "removed_vote") {
        showToast(`Devoted: Removed vote for "${habit.title}" from DB & logs`);
      } else {
        showToast(`Devoted (${res.timestamp}): Logged -1 vote for "${habit.title}"`);
      }
      await loadState();
    });
  });

  // Bind delete habit buttons
  grid.querySelectorAll("[data-del-habit]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const habit = state.data.habits.find((h) => h.id === btn.dataset.delHabit);
      if (!habit) return;
      await api(`/api/habits/${encodeURIComponent(habit.id)}`, { method: "DELETE" });
      showToast(`Deleted habit "${habit.title}" from DB & logs`);
      await loadState();
    });
  });

  // Bind delete identity buttons
  grid.querySelectorAll("[data-del-ident]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ident = state.data.identities.find((i) => i.id === btn.dataset.delIdent);
      if (!ident) return;
      await api(`/api/identities/${encodeURIComponent(ident.id)}`, { method: "DELETE" });
      showToast(`Deleted identity "${ident.name}" from DB & logs`);
      await loadState();
    });
  });

  // Bind inline stage selector
  grid.querySelectorAll("[data-stage-ident]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const identId = sel.dataset.stageIdent;
      await api(`/api/identities/${encodeURIComponent(identId)}`, {
        method: "PUT",
        body: JSON.stringify({ current_stage: sel.value }),
      });
      showToast("Updated identity stage");
      await loadState();
    });
  });

  // Bind + Habit & Edit buttons
  grid.querySelectorAll("[data-add-habit-for]").forEach((btn) => {
    btn.addEventListener("click", () => openHabitModal(null, [btn.dataset.addHabitFor], "identity_habit"));
  });
  grid.querySelectorAll("[data-edit-habit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const h = state.data.habits.find((x) => x.id === btn.dataset.editHabit);
      if (h) openHabitModal(h);
    });
  });
  grid.querySelectorAll("[data-edit-ident]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ident = state.data.identities.find((x) => x.id === btn.dataset.editIdent);
      if (ident) openIdentityModal(ident);
    });
  });
}

/* -------------------------------------------------------------------------- */
/* Anti-Identity Guardrails & Evidence Activity Feed                          */
/* -------------------------------------------------------------------------- */
function renderGuardrailsAndFeed() {
  const { habits, actions, identities, settings } = state.data;
  document.getElementById("antiPrincipleDisplay").textContent =
    settings.anti_principle || "I am not trying to eliminate fun. I am choosing how fun fits into my life.";

  const guardList = document.getElementById("guardrailsList");
  guardList.innerHTML = "";
  const guardrails = habits.filter((h) => h.category === "anti_identity_guard");

  for (const g of guardrails) {
    const done = g.completed_on_selected_date || 0;
    const item = document.createElement("div");
    item.className = `habit-item ${done > 0 ? "completed-today" : ""}`;
    const text = state.twoMinuteMode && g.two_minute_version ? g.two_minute_version : g.title;
    item.innerHTML = `
      <div class="habit-text-wrap">
        <span class="habit-title-text">${escapeHtml(text)}</span>
      </div>
      <div class="habit-actions">
        <button type="button" class="btn-vote-sm" data-guard-vote="${escapeHtml(g.id)}">
          ${done > 0 ? `✓ Held (${done})` : "+ Held Boundary"}
        </button>
        <button type="button" class="btn-devote-sm" title="Devote guardrail" data-guard-devote="${escapeHtml(g.id)}">
          − Devote
        </button>
        <button type="button" class="icon-btn-sm" title="Log slip/obstacle for this guardrail" data-guard-slip="${escapeHtml(g.id)}">⚠</button>
        <button type="button" class="icon-btn-sm" title="Edit guardrail" data-edit-guard="${escapeHtml(g.id)}">✎</button>
        <button type="button" class="icon-btn-sm" title="Delete guardrail" data-del-guard="${escapeHtml(g.id)}">✕</button>
      </div>
    `;
    guardList.appendChild(item);
  }

  guardList.querySelectorAll("[data-guard-vote]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const g = guardrails.find((x) => x.id === btn.dataset.guardVote);
      if (!g) return;
      const res = await api("/api/actions", {
        method: "POST",
        body: JSON.stringify({
          habit_id: g.id,
          title: g.title,
          action_date: state.selectedDate,
          identity_ids: g.identity_ids,
          used_two_minute_rule: state.twoMinuteMode,
          kind: "vote",
        }),
      });
      showToast(`Boundary win recorded (${res.timestamp})`);
      await loadState();
    });
  });

  guardList.querySelectorAll("[data-guard-devote]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const g = guardrails.find((x) => x.id === btn.dataset.guardDevote);
      if (!g) return;
      await api("/api/actions/devote", {
        method: "POST",
        body: JSON.stringify({
          habit_id: g.id,
          action_date: state.selectedDate,
          identity_ids: g.identity_ids,
        }),
      });
      showToast(`Devoted guardrail: ${g.title}`);
      await loadState();
    });
  });

  guardList.querySelectorAll("[data-guard-slip]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const g = guardrails.find((x) => x.id === btn.dataset.guardSlip);
      if (!g) return;
      const cue = window.prompt("What environmental cue or friction triggered this slip? (Optional note)", "") ?? "";
      await api("/api/actions", {
        method: "POST",
        body: JSON.stringify({
          habit_id: g.id,
          title: `Friction on: ${g.title}`,
          evidence_note: cue,
          action_date: state.selectedDate,
          identity_ids: g.identity_ids,
          kind: "obstacle",
        }),
      });
      showToast("Logged as obstacle data for Weekly Review");
      await loadState();
    });
  });

  guardList.querySelectorAll("[data-edit-guard]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const g = guardrails.find((x) => x.id === btn.dataset.editGuard);
      if (g) openHabitModal(g);
    });
  });

  guardList.querySelectorAll("[data-del-guard]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const g = guardrails.find((x) => x.id === btn.dataset.delGuard);
      if (!g) return;
      await api(`/api/habits/${encodeURIComponent(g.id)}`, { method: "DELETE" });
      showToast(`Deleted guardrail "${g.title}"`);
      await loadState();
    });
  });

  // Populate Feed Filter
  const filterSelect = document.getElementById("feedIdentityFilter");
  const prevVal = state.feedFilter;
  filterSelect.innerHTML = `<option value="all">All Identities (${actions.length})</option>`;
  for (const ident of identities) {
    const opt = document.createElement("option");
    opt.value = ident.id;
    opt.textContent = ident.name;
    filterSelect.appendChild(opt);
  }
  filterSelect.value = identities.some((i) => i.id === prevVal) ? prevVal : "all";

  // Render Evidence Feed with Full Timestamp (DD/MM/YYYY HH:MM:SS)
  const feedEl = document.getElementById("evidenceFeedList");
  feedEl.innerHTML = "";
  const filtered =
    filterSelect.value === "all"
      ? actions
      : actions.filter((a) => a.identity_ids.includes(filterSelect.value));

  if (filtered.length === 0) {
    feedEl.innerHTML = `<p class="card-subtitle">No actions logged for this selection yet.</p>`;
    return;
  }

  for (const act of filtered) {
    const row = document.createElement("div");
    const kindClass = act.kind === "obstacle" ? "obstacle" : act.kind === "devote" ? "devote" : "";
    row.className = `feed-item ${kindClass}`;
    const badges = act.identities
      .map(
        (idObj) =>
          `<span class="mini-badge"><span style="color:${identColor(idObj)}">●</span> ${escapeHtml(idObj.name)}</span>`
      )
      .join("");
    const weightBadge =
      (act.kind === "vote" || act.kind === "devote") && act.identities.length >= 1
        ? `<span class="mini-badge">${act.fractional_weight > 0 ? `+${act.fractional_weight}` : act.fractional_weight} wt</span>`
        : "";
    const twoMinBadge = act.used_two_minute_rule ? `<span class="mini-badge">⚡ 2-Min Rule</span>` : "";
    const kindBadge =
      act.kind === "obstacle"
        ? `<span class="mini-badge" style="color:var(--warn)">⚠ Obstacle</span>`
        : act.kind === "devote"
        ? `<span class="mini-badge" style="color:var(--danger)">− Devote</span>`
        : `<span class="mini-badge" style="color:var(--good)">+ Vote</span>`;

    const fullTimestamp = act.timestamp_display || act.created_at || `${act.action_date} ${act.action_time || ""}`;

    row.innerHTML = `
      <div>
        <div class="feed-item-title">${escapeHtml(act.title)}</div>
        ${act.evidence_note ? `<div class="feed-item-note">${escapeHtml(act.evidence_note)}</div>` : ""}
        <div class="feed-item-meta">
          <span class="mini-badge" title="Day/Month/Year Hour:Minute:Second">🕒 ${escapeHtml(fullTimestamp)}</span>
          ${kindBadge}
          ${twoMinBadge}
          ${badges}
          ${weightBadge}
        </div>
      </div>
      <div class="habit-actions">
        ${
          act.kind === "vote"
            ? `<button type="button" class="btn-devote-sm" title="Devote / remove this vote from DB & logs" data-devote-action="${act.id}">− Devote</button>`
            : ""
        }
        <button type="button" class="icon-btn-sm" title="Delete log entry" data-del-action="${act.id}">✕</button>
      </div>
    `;
    feedEl.appendChild(row);
  }

  feedEl.querySelectorAll("[data-devote-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api("/api/actions/devote", {
        method: "POST",
        body: JSON.stringify({ action_id: Number(btn.dataset.devoteAction) }),
      });
      showToast("Vote devoted & removed from database and logs");
      await loadState();
    });
  });

  feedEl.querySelectorAll("[data-del-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/actions/${btn.dataset.delAction}`, { method: "DELETE" });
      showToast("Deleted entry from database and logs");
      await loadState();
    });
  });
}

/* -------------------------------------------------------------------------- */
/* Weekly Review View                                                         */
/* -------------------------------------------------------------------------- */
function renderWeeklyReview() {
  const { weekly_review, week_start, week_end, settings } = state.data;
  const { auto_summary, saved } = weekly_review;

  document.getElementById("reviewWeekSub").textContent = `Week of ${week_start} to ${week_end}`;

  const supEl = document.getElementById("revSupportedList");
  supEl.innerHTML = auto_summary.supported_identities.length
    ? auto_summary.supported_identities
        .map(
          (s) =>
            `<div><strong>${escapeHtml(s.name)}</strong>: ${s.weighted_votes} net votes (${s.percentage}%) across ${s.raw_touches} actions</div>`
        )
        .join("")
    : `<div class="card-subtitle">No net votes recorded this week yet.</div>`;

  const negEl = document.getElementById("revNeglectedList");
  negEl.innerHTML = auto_summary.neglected_identities.length
    ? auto_summary.neglected_identities
        .map((n) => `<div>• ${escapeHtml(n.name)} (0 net votes this week)</div>`)
        .join("")
    : `<div>All active identities received positive net votes this week!</div>`;

  const repEl = document.getElementById("revRepeatedList");
  repEl.innerHTML = auto_summary.repeated_behaviors.length
    ? auto_summary.repeated_behaviors
        .map((r) => `<div>↻ <strong>${escapeHtml(r.title)}</strong> (${r.count}× this week)</div>`)
        .join("")
    : `<div class="card-subtitle">No single behavior repeated 2+ times yet this week.</div>`;

  const obsEl = document.getElementById("revObstaclesList");
  obsEl.innerHTML = auto_summary.obstacles.length
    ? auto_summary.obstacles
        .map(
          (o) =>
            `<div>${o.kind === "devote" ? "−" : "⚠"} <strong>${escapeHtml(o.title)}</strong> (${escapeHtml(o.timestamp_display || o.action_date)}) ${o.evidence_note ? `— ${escapeHtml(o.evidence_note)}` : ""}</div>`
        )
        .join("")
    : `<div>No devotes or obstacles logged this week.</div>`;

  const highEl = document.getElementById("revHighlightsList");
  highEl.innerHTML = auto_summary.strongest_candidates.length
    ? auto_summary.strongest_candidates
        .map(
          (c) =>
            `<div>★ <strong>${escapeHtml(c.title)}</strong> (${escapeHtml(c.timestamp_display || c.action_date)}) ${c.evidence_note ? `— <em>${escapeHtml(c.evidence_note)}</em>` : ""}</div>`
        )
        .join("")
    : `<div class="card-subtitle">Add an evidence note when logging actions to highlight breakthroughs here.</div>`;

  const qContainer = document.getElementById("reviewQuestionsContainer");
  qContainer.innerHTML = "";
  const questions = settings.reflection_questions || [];
  const savedAnswers = saved.answers || {};

  questions.forEach((qText, idx) => {
    const qKey = `q_${idx}`;
    const val = savedAnswers[qText] ?? savedAnswers[qKey] ?? "";
    const div = document.createElement("div");
    div.className = "form-group";
    div.innerHTML = `
      <label><strong>${escapeHtml(qText)}</strong></label>
      <textarea class="input-main" rows="2" data-review-question="${escapeHtml(qText)}">${escapeHtml(val)}</textarea>
    `;
    qContainer.appendChild(div);
  });

  document.getElementById("revOneAdjustment").value = saved.one_adjustment || "";
  document.getElementById("revStrongestEvidence").value = saved.strongest_evidence || "";
  document.getElementById("revNextSmallestAction").value = saved.next_smallest_action || "";

  const stageSel = document.getElementById("revOverallStage");
  const stages = (settings.stages || []).map((s) => s.name || s);
  stageSel.innerHTML = stages
    .map(
      (st) =>
        `<option value="${escapeHtml(st)}" ${st === saved.overall_stage ? "selected" : ""}>${escapeHtml(st)}</option>`
    )
    .join("");

  const checksGrid = document.getElementById("revSystemChecksGrid");
  checksGrid.innerHTML = "";
  const sysChecks = settings.system_checks || [];
  const savedChecks = saved.system_checks || {};
  for (const chk of sysChecks) {
    const checked = Boolean(savedChecks[chk.id]);
    const lbl = document.createElement("label");
    lbl.className = "check-label";
    lbl.innerHTML = `
      <input type="checkbox" data-sys-check="${escapeHtml(chk.id)}" ${checked ? "checked" : ""} />
      <span><strong>[${escapeHtml(chk.group)}]</strong> ${escapeHtml(chk.label)}</span>
    `;
    checksGrid.appendChild(lbl);
  }
}

/* -------------------------------------------------------------------------- */
/* Markdown Guidance View (External .md Files + Live Editor)                  */
/* -------------------------------------------------------------------------- */
function simpleMarkdownToHtml(md) {
  const lines = String(md || "").split(/\r?\n/);
  let html = "";
  let inList = false;
  let inTable = false;

  const closeList = () => {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  };
  const closeTable = () => {
    if (inTable) {
      html += "</tbody></table>";
      inTable = false;
    }
  };

  const inlineFmt = (txt) =>
    escapeHtml(txt)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>");

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      closeList();
      closeTable();
      continue;
    }
    if (line === "---") {
      closeList();
      closeTable();
      html += "<hr />";
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      closeTable();
      html += `<h1>${inlineFmt(line.slice(2))}</h1>`;
      continue;
    }
    if (line.startsWith("## ")) {
      closeList();
      closeTable();
      html += `<h2>${inlineFmt(line.slice(3))}</h2>`;
      continue;
    }
    if (line.startsWith("### ")) {
      closeList();
      closeTable();
      html += `<h3>${inlineFmt(line.slice(4))}</h3>`;
      continue;
    }
    if (line.startsWith(">")) {
      closeList();
      closeTable();
      html += `<blockquote>${inlineFmt(line.replace(/^>\s*/, ""))}</blockquote>`;
      continue;
    }
    if (line.startsWith("|") && line.endsWith("|")) {
      closeList();
      const cells = line
        .slice(1, -1)
        .split("|")
        .map((c) => c.trim());
      if (cells.every((c) => /^[:\-]+$/.test(c))) continue;
      if (!inTable) {
        html += "<table><thead><tr>" + cells.map((c) => `<th>${inlineFmt(c)}</th>`).join("") + "</tr></thead><tbody>";
        inTable = true;
      } else {
        html += "<tr>" + cells.map((c) => `<td>${inlineFmt(c)}</td>`).join("") + "</tr>";
      }
      continue;
    }
    if (line.startsWith("- ") || /^\d+\.\s+/.test(line)) {
      closeTable();
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      const itemTxt = line.replace(/^(-\s+|\d+\.\s+)/, "");
      html += `<li>${inlineFmt(itemTxt)}</li>`;
      continue;
    }
    closeList();
    closeTable();
    html += `<p>${inlineFmt(line)}</p>`;
  }
  closeList();
  closeTable();
  return html;
}

function renderGuidanceView() {
  const listEl = document.getElementById("guidanceDocList");
  listEl.innerHTML = "";

  for (const doc of state.guidanceDocs) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `guidance-nav-item ${doc.id === state.activeGuidanceId ? "active" : ""}`;
    btn.innerHTML = `
      <span class="guidance-nav-title">${escapeHtml(doc.title)}</span>
      <span class="guidance-nav-sub">${escapeHtml(doc.filename)}</span>
    `;
    btn.addEventListener("click", () => {
      state.activeGuidanceId = doc.id;
      state.editingGuidance = false;
      renderGuidanceView();
    });
    listEl.appendChild(btn);
  }

  const activeDoc = state.guidanceDocs.find((d) => d.id === state.activeGuidanceId);
  const renderedEl = document.getElementById("guidanceRenderedView");
  const editorWrap = document.getElementById("guidanceEditorWrap");
  const saveBtn = document.getElementById("saveGuidanceBtn");
  const toggleBtn = document.getElementById("toggleEditGuidanceBtn");

  if (state.editingGuidance) {
    renderedEl.hidden = true;
    editorWrap.hidden = false;
    saveBtn.hidden = false;
    toggleBtn.textContent = "Cancel Edit";
    document.getElementById("guidanceIdInput").value = activeDoc ? activeDoc.id : "";
    document.getElementById("guidanceMarkdownTextarea").value = activeDoc ? activeDoc.markdown : "# New Guidance Document\n\n";
  } else {
    renderedEl.hidden = false;
    editorWrap.hidden = true;
    saveBtn.hidden = true;
    toggleBtn.textContent = "Edit Markdown";
    if (activeDoc) {
      document.getElementById("guidanceFileBadge").textContent = activeDoc.filename;
      document.getElementById("guidanceDocTitle").textContent = activeDoc.title;
      renderedEl.innerHTML = simpleMarkdownToHtml(activeDoc.markdown);
    } else {
      renderedEl.innerHTML = "<p>No Markdown files found in <code>guidance/</code>.</p>";
    }
  }
}

/* -------------------------------------------------------------------------- */
/* Extend & Configure View (Identities, Habits & Settings)                    */
/* -------------------------------------------------------------------------- */
function renderManageView() {
  const listEl = document.getElementById("manageIdentitiesList");
  listEl.innerHTML = "";
  const { identities, habits, settings } = state.data;

  for (const ident of identities) {
    const row = document.createElement("div");
    row.className = "manage-row";
    row.innerHTML = `
      <div class="legend-ident-cell">
        <span class="legend-swatch" style="background:${identColor(ident)}"></span>
        <div>
          <strong>${escapeHtml(ident.name)}</strong>
          <div class="card-subtitle">${escapeHtml(ident.tagline)} · Stage: ${escapeHtml(ident.current_stage)}</div>
        </div>
      </div>
      <div class="habit-actions">
        <button type="button" class="btn-secondary" data-mgr-edit="${escapeHtml(ident.id)}">Edit</button>
        <button type="button" class="btn-devote-sm" title="Delete identity" data-mgr-del="${escapeHtml(ident.id)}">Delete</button>
      </div>
    `;
    listEl.appendChild(row);
  }

  listEl.querySelectorAll("[data-mgr-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ident = identities.find((i) => i.id === btn.dataset.mgrEdit);
      if (ident) openIdentityModal(ident);
    });
  });

  listEl.querySelectorAll("[data-mgr-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ident = identities.find((i) => i.id === btn.dataset.mgrDel);
      if (!ident) return;
      await api(`/api/identities/${encodeURIComponent(ident.id)}`, { method: "DELETE" });
      showToast(`Deleted identity "${ident.name}"`);
      await loadState();
    });
  });

  const habitsListEl = document.getElementById("manageHabitsList");
  if (habitsListEl) {
    habitsListEl.innerHTML = "";
    const identMap = Object.fromEntries(identities.map((i) => [i.id, i.name]));
    for (const h of habits) {
      const row = document.createElement("div");
      row.className = "manage-row";
      const linkedNames = (h.identity_ids || []).map((id) => identMap[id] || id).join(", ");
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(h.title)}</strong>
          <div class="card-subtitle">
            ${escapeHtml(h.category === "anti_identity_guard" ? "Anti-Identity Guardrail" : "Habit")}
            · ${escapeHtml(h.cadence)}
            · Linked: ${escapeHtml(linkedNames)}
          </div>
        </div>
        <div class="habit-actions">
          <button type="button" class="btn-secondary" data-mgr-habit-edit="${escapeHtml(h.id)}">Edit</button>
          <button type="button" class="btn-devote-sm" title="Delete habit" data-mgr-habit-del="${escapeHtml(h.id)}">Delete</button>
        </div>
      `;
      habitsListEl.appendChild(row);
    }

    habitsListEl.querySelectorAll("[data-mgr-habit-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const h = habits.find((x) => x.id === btn.dataset.mgrHabitEdit);
        if (h) openHabitModal(h);
      });
    });

    habitsListEl.querySelectorAll("[data-mgr-habit-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const h = habits.find((x) => x.id === btn.dataset.mgrHabitDel);
        if (!h) return;
        await api(`/api/habits/${encodeURIComponent(h.id)}`, { method: "DELETE" });
        showToast(`Deleted "${h.title}"`);
        await loadState();
      });
    });
  }

  document.getElementById("settingAntiPrinciple").value = settings.anti_principle || "";
  document.getElementById("settingQuestionsTextarea").value = (settings.reflection_questions || []).join("\n");
}

/* -------------------------------------------------------------------------- */
/* Modals for Extending Identities & Habits                                   */
/* -------------------------------------------------------------------------- */
function openIdentityModal(ident = null) {
  const modal = document.getElementById("identityModal");
  document.getElementById("identityModalTitle").textContent = ident ? "Edit Identity" : "New Identity";
  document.getElementById("identModalId").value = ident ? ident.id : "";
  document.getElementById("identModalName").value = ident ? ident.name : "";
  document.getElementById("identModalTagline").value = ident ? ident.tagline : "";
  document.getElementById("identModalDomain").value = ident ? ident.domain || "general" : "work";

  const stages = (state.data.settings.stages || []).map((s) => s.name || s);
  const stageSel = document.getElementById("identModalStage");
  stageSel.innerHTML = stages.map((st) => `<option value="${escapeHtml(st)}">${escapeHtml(st)}</option>`).join("");
  stageSel.value = ident ? ident.current_stage : "Building evidence";

  const slots = state.data.palette_slots || [{ light: "#2a78d6", dark: "#3987e5" }];
  const nextSlot = slots[state.data.identities.length % slots.length];
  document.getElementById("identModalColorLight").value = ident ? ident.color_light : nextSlot.light;
  document.getElementById("identModalColorDark").value = ident ? ident.color_dark : nextSlot.dark;

  modal.hidden = false;
}

function openHabitModal(habit = null, defaultIdentityIds = [], defaultCategory = "identity_habit") {
  const modal = document.getElementById("habitModal");
  document.getElementById("habitModalTitle").textContent = habit ? "Edit Recurring Habit / Guardrail" : "New Recurring Habit";
  document.getElementById("habitModalId").value = habit ? habit.id : "";
  document.getElementById("habitModalTitleInput").value = habit ? habit.title : "";
  document.getElementById("habitModalTwoMinInput").value = habit ? habit.two_minute_version : "";
  document.getElementById("habitModalCadence").value = habit ? habit.cadence : "daily";
  document.getElementById("habitModalCategory").value = habit ? habit.category : defaultCategory;

  state.modalHabitIdentities = new Set(
    habit ? habit.identity_ids : defaultIdentityIds.length ? defaultIdentityIds : [state.data.identities[0]?.id].filter(Boolean)
  );
  renderHabitModalIdentityPills();
  modal.hidden = false;
}

function renderHabitModalIdentityPills() {
  const wrap = document.getElementById("habitModalIdentityPills");
  wrap.innerHTML = "";
  for (const ident of state.data.identities) {
    const btn = document.createElement("button");
    btn.type = "button";
    const sel = state.modalHabitIdentities.has(ident.id);
    btn.className = `identity-pill ${sel ? "selected" : ""}`;
    btn.innerHTML = `<span class="swatch" style="background:${identColor(ident)}"></span><span>${escapeHtml(ident.name)}</span>`;
    btn.addEventListener("click", () => {
      if (state.modalHabitIdentities.has(ident.id)) {
        if (state.modalHabitIdentities.size > 1) state.modalHabitIdentities.delete(ident.id);
      } else {
        state.modalHabitIdentities.add(ident.id);
      }
      renderHabitModalIdentityPills();
    });
    wrap.appendChild(btn);
  }
}

/* -------------------------------------------------------------------------- */
/* Event Wiring                                                               */
/* -------------------------------------------------------------------------- */
function switchView(viewName) {
  state.view = viewName;
  document.querySelectorAll(".nav-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === viewName);
  });
  document.querySelectorAll(".view-panel").forEach((p) => {
    p.hidden = p.id !== `view-${viewName}`;
  });
  if (viewName === "guidance" && state.guidanceDocs.length === 0) {
    loadGuidance();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  document.querySelectorAll("[data-jump-view]").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.jumpView));
  });

  document.getElementById("twoMinModeBtn").addEventListener("click", (e) => {
    state.twoMinuteMode = !state.twoMinuteMode;
    e.currentTarget.classList.toggle("active", state.twoMinuteMode);
    document.getElementById("actionTwoMinCheck").checked = state.twoMinuteMode;
    renderIdentityCards();
    renderGuardrailsAndFeed();
  });

  document.getElementById("themeToggleBtn").addEventListener("click", () => {
    const next = isDarkMode() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    renderAll();
  });

  document.querySelectorAll(".scope-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.scope = btn.dataset.scope;
      loadState();
    });
  });

  document.getElementById("selectedDateInput").addEventListener("change", (e) => {
    state.selectedDate = e.target.value;
    loadState();
  });

  const shiftDate = (days) => {
    const d = new Date(`${state.selectedDate}T12:00:00`);
    d.setDate(d.getDate() + days);
    state.selectedDate = d.toISOString().slice(0, 10);
    loadState();
  };
  document.getElementById("prevDayBtn").addEventListener("click", () => shiftDate(-1));
  document.getElementById("nextDayBtn").addEventListener("click", () => shiftDate(1));
  document.getElementById("todayBtn").addEventListener("click", () => {
    state.selectedDate = state.data.today;
    loadState();
  });

  // Quick-Capture kind switch (vote vs devote vs obstacle)
  document.querySelectorAll(".kind-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.captureKind = btn.dataset.kind;
      document.querySelectorAll(".kind-btn").forEach((b) => b.classList.toggle("active", b === btn));
      const submitBtn = document.getElementById("submitActionBtn");
      if (state.captureKind === "obstacle") {
        submitBtn.textContent = "Log Obstacle";
      } else if (state.captureKind === "devote") {
        submitBtn.textContent = "Cast Devote (−1)";
      } else {
        submitBtn.textContent = "Cast Vote";
      }
    });
  });

  // Quick-Capture Submit
  document.getElementById("quickCaptureForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const titleEl = document.getElementById("actionTitleInput");
    const noteEl = document.getElementById("actionEvidenceInput");
    const twoMinEl = document.getElementById("actionTwoMinCheck");

    const res = await api("/api/actions", {
      method: "POST",
      body: JSON.stringify({
        title: titleEl.value,
        evidence_note: noteEl.value,
        action_date: state.selectedDate,
        kind: state.captureKind,
        used_two_minute_rule: twoMinEl.checked,
        identity_ids: Array.from(state.selectedCaptureIdentities),
      }),
    });

    titleEl.value = "";
    noteEl.value = "";
    showToast(
      state.captureKind === "obstacle"
        ? `Obstacle logged (${res.timestamp})`
        : state.captureKind === "devote"
        ? `Devote logged (${res.timestamp})`
        : `Identity vote cast (${res.timestamp})!`
    );
    await loadState();
  });

  document.getElementById("feedIdentityFilter").addEventListener("change", (e) => {
    state.feedFilter = e.target.value;
    renderGuardrailsAndFeed();
  });

  document.getElementById("openNewIdentityModalBtn").addEventListener("click", () => openIdentityModal(null));
  document.getElementById("manageAddIdentityBtn").addEventListener("click", () => openIdentityModal(null));
  document.getElementById("openNewHabitModalBtn").addEventListener("click", () => openHabitModal(null));
  const mgrAddHabitBtn = document.getElementById("manageAddHabitBtn");
  if (mgrAddHabitBtn) {
    mgrAddHabitBtn.addEventListener("click", () => openHabitModal(null));
  }
  document.getElementById("addGuardrailBtn").addEventListener("click", () =>
    openHabitModal(null, [], "anti_identity_guard")
  );

  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById(btn.dataset.closeModal).hidden = true;
    });
  });

  document.getElementById("identityModalForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("identModalId").value;
    const payload = {
      name: document.getElementById("identModalName").value,
      tagline: document.getElementById("identModalTagline").value,
      domain: document.getElementById("identModalDomain").value,
      current_stage: document.getElementById("identModalStage").value,
      color_light: document.getElementById("identModalColorLight").value,
      color_dark: document.getElementById("identModalColorDark").value,
    };
    if (id) {
      await api(`/api/identities/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(payload) });
      showToast("Identity updated");
    } else {
      await api("/api/identities", { method: "POST", body: JSON.stringify(payload) });
      showToast("New identity created");
    }
    document.getElementById("identityModal").hidden = true;
    await loadState();
  });

  document.getElementById("habitModalForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("habitModalId").value;
    const payload = {
      title: document.getElementById("habitModalTitleInput").value,
      two_minute_version: document.getElementById("habitModalTwoMinInput").value,
      cadence: document.getElementById("habitModalCadence").value,
      category: document.getElementById("habitModalCategory").value,
      identity_ids: Array.from(state.modalHabitIdentities),
    };
    if (id) {
      await api(`/api/habits/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(payload) });
      showToast("Habit updated");
    } else {
      await api("/api/habits", { method: "POST", body: JSON.stringify(payload) });
      showToast("New habit added");
    }
    document.getElementById("habitModal").hidden = true;
    await loadState();
  });

  document.getElementById("prefillReviewBtn").addEventListener("click", () => {
    const { auto_summary } = state.data.weekly_review;
    const textareas = document.querySelectorAll("[data-review-question]");
    if (textareas[0] && !textareas[0].value.trim()) {
      textareas[0].value = auto_summary.suggested_supported;
    }
    if (textareas[1] && !textareas[1].value.trim()) {
      textareas[1].value = auto_summary.suggested_contradicted;
    }
    const strongEl = document.getElementById("revStrongestEvidence");
    if (!strongEl.value.trim() && auto_summary.strongest_candidates.length > 0) {
      strongEl.value = auto_summary.strongest_candidates[0].title;
    }
    showToast("Pre-filled reflection fields from this week's evidence");
  });

  document.getElementById("weeklyReviewForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const answers = {};
    document.querySelectorAll("[data-review-question]").forEach((ta) => {
      answers[ta.dataset.reviewQuestion] = ta.value;
    });
    const checks = {};
    document.querySelectorAll("[data-sys-check]").forEach((chk) => {
      checks[chk.dataset.sysCheck] = chk.checked;
    });

    const res = await api("/api/weekly-review", {
      method: "POST",
      body: JSON.stringify({
        week_start: state.data.week_start,
        answers,
        one_adjustment: document.getElementById("revOneAdjustment").value,
        strongest_evidence: document.getElementById("revStrongestEvidence").value,
        next_smallest_action: document.getElementById("revNextSmallestAction").value,
        overall_stage: document.getElementById("revOverallStage").value,
        system_checks: checks,
      }),
    });
    document.getElementById("reviewSaveStatus").textContent = `✓ Saved (${res.review_date}) & pinned to Dashboard`;
    showToast("Weekly review saved!");
    await loadState();
  });

  document.getElementById("newGuidanceDocBtn").addEventListener("click", () => {
    state.activeGuidanceId = null;
    state.editingGuidance = true;
    renderGuidanceView();
  });
  document.getElementById("toggleEditGuidanceBtn").addEventListener("click", () => {
    state.editingGuidance = !state.editingGuidance;
    renderGuidanceView();
  });
  document.getElementById("saveGuidanceBtn").addEventListener("click", async () => {
    const idVal = document.getElementById("guidanceIdInput").value.trim() || state.activeGuidanceId || "custom-guide";
    const mdVal = document.getElementById("guidanceMarkdownTextarea").value;
    const res = await api("/api/guidance", {
      method: "POST",
      body: JSON.stringify({ id: idVal, markdown: mdVal }),
    });
    state.activeGuidanceId = res.id;
    state.editingGuidance = false;
    showToast(`Saved ${res.filename}`);
    await loadGuidance();
  });

  document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
    const antiPrinciple = document.getElementById("settingAntiPrinciple").value.trim();
    const questions = document
      .getElementById("settingQuestionsTextarea")
      .value.split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        anti_principle: antiPrinciple,
        reflection_questions: questions,
      }),
    });
    document.getElementById("settingsSaveStatus").textContent = "✓ Saved settings";
    showToast("System settings updated");
    await loadState();
  });

  loadState();
});
