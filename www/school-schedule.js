/* School schedule more-info: period table instead of history/attributes.
   Matches any sensor.*_schedule_today entity published by the Infinite Campus poller. */
const SCHED_RE = /^sensor\.[a-z0-9_]+_schedule_today$/;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const RANGE_RE =
  /\(?\s*(\d{1,2}:\d{2})\s*(a\.?m\.?|p\.?m\.?)?\s*[-–]\s*(\d{1,2}:\d{2})\s*(a\.?m\.?|p\.?m\.?)?\s*\)?/i;

function meridiem(hhmm, token) {
  if (token) return token.toLowerCase().startsWith("p") ? "PM" : "AM";
  const h = parseInt(String(hhmm).split(":")[0], 10);
  if (h === 12 || (h >= 1 && h <= 6)) return "PM";
  return "AM";
}

function toMinutes(hhmm, mer) {
  const parts = String(hhmm).split(":");
  let h = parseInt(parts[0], 10);
  const m = parseInt(parts[1] || "0", 10);
  if (h === 12) h = mer === "PM" ? 12 : 0;
  else if (mer === "PM") h += 12;
  return h * 60 + m;
}

function hhmmss(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
}

function splitTeacherTimes(teacher) {
  const s = String(teacher || "");
  const m = s.match(RANGE_RE);
  if (!m) return { teacher: s.trim(), start: "", end: "" };
  const startMer = meridiem(m[1], m[2]);
  const endMer = meridiem(m[3], m[4]);
  const name = s
    .replace(RANGE_RE, "")
    .replace(/\s+/g, " ")
    .replace(/[()\s,]+$/g, "")
    .trim();
  return {
    teacher: name,
    start: hhmmss(toMinutes(m[1], startMer)),
    end: hhmmss(toMinutes(m[3], endMer)),
  };
}

function minutesFromHms(value) {
  const s = String(value || "").trim();
  const m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return 24 * 60 + 1;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function fmtTime(value) {
  const s = String(value || "").trim();
  const m = s.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return s;
  let h = parseInt(m[1], 10);
  const min = m[2];
  const ap = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${min} ${ap}`;
}

function normalizePeriod(p) {
  const parsed = splitTeacherTimes(p.teacher || "");
  const start = parsed.start || p.start || "";
  const end = parsed.end || p.end || "";
  return {
    period: p.period || "",
    course: p.course || "",
    room: p.room || "",
    teacher: parsed.start ? parsed.teacher : p.teacher || "",
    start,
    end,
    sort: minutesFromHms(start),
  };
}

function tableHtml(periods) {
  if (!periods || !periods.length) {
    return `<p class="school-sched-empty">No school today</p>`;
  }
  const rows = periods
    .map(normalizePeriod)
    .sort((a, b) => a.sort - b.sort || a.course.localeCompare(b.course))
    .map((p) => {
      const start = fmtTime(p.start);
      const end = fmtTime(p.end);
      const time = start && end ? `${start} – ${end}` : start || end;
      return `<tr>
        <td>${escapeHtml(p.period)}</td>
        <td>${escapeHtml(time)}</td>
        <td>${escapeHtml(p.course)}</td>
        <td>${escapeHtml(p.teacher)}</td>
        <td>${escapeHtml(p.room)}</td>
      </tr>`;
    })
    .join("");
  return `<table class="school-sched">
    <thead><tr><th>Period</th><th>Time</th><th>Course</th><th>Teacher</th><th>Room</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function paint(el) {
  const root = el.shadowRoot;
  if (!root) return;
  const entityId = el.entityId;
  const content = root.querySelector(".content");
  if (!content) return;

  const existing = content.querySelector("#school-sched");
  if (!entityId || !SCHED_RE.test(entityId)) {
    if (existing) existing.remove();
    for (const child of content.children) child.style.removeProperty("display");
    return;
  }

  const hass = el.hass || document.querySelector("home-assistant")?.hass;
  const periods = hass?.states?.[entityId]?.attributes?.periods || [];

  for (const child of [...content.children]) {
    if (child.id !== "school-sched") child.style.display = "none";
  }

  let box = existing;
  if (!box) {
    box = document.createElement("div");
    box.id = "school-sched";
    content.appendChild(box);
    const style = document.createElement("style");
    style.textContent = `
      #school-sched { width: 100%; overflow-x: auto; }
      #school-sched .school-sched {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
      }
      #school-sched th, #school-sched td {
        text-align: left;
        padding: 8px 10px;
        border-bottom: 1px solid var(--divider-color, rgba(255,255,255,.12));
        vertical-align: top;
      }
      #school-sched th {
        color: var(--secondary-text-color);
        font-weight: 600;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: .04em;
      }
      #school-sched td { color: var(--primary-text-color); }
      #school-sched tr:last-child td { border-bottom: none; }
      #school-sched .school-sched-empty {
        margin: 0;
        color: var(--secondary-text-color);
      }
    `;
    box.appendChild(style);
    const holder = document.createElement("div");
    holder.className = "school-sched-html";
    box.appendChild(holder);
  }
  const holder = box.querySelector(".school-sched-html");
  if (holder) holder.innerHTML = tableHtml(periods);
}

function wrapUpdated(tag, fn, flag) {
  customElements.whenDefined(tag).then(() => {
    const Cls = customElements.get(tag);
    if (!Cls || Cls[flag]) return;
    Cls[flag] = true;
    const orig = Cls.prototype.updated;
    Cls.prototype.updated = function campusParentUpdated() {
      if (typeof orig === "function") orig.apply(this, arguments);
      try {
        requestAnimationFrame(() => fn(this));
      } catch (err) {
        console.warn("school-schedule", err);
      }
    };
  });
}

const GRADE_GREEN = "#4ade80";
const GRADE_ORANGE = "#fb923c";
const GRADE_RED = "#f87171";

function colorForPct(pct) {
  if (pct > 89.9) return GRADE_GREEN;
  if (pct > 79.9) return GRADE_ORANGE;
  return GRADE_RED;
}

function paintGradeNodes(root) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll(".school-missing").forEach((n) => {
    n.style.color = GRADE_RED;
    n.style.fontWeight = "600";
  });
  root.querySelectorAll(".school-grade").forEach((n) => {
    const pct = parseFloat(n.getAttribute("data-pct"));
    if (Number.isNaN(pct)) return;
    n.style.color = colorForPct(pct);
    n.style.fontWeight = "600";
  });
}

function paintMarkdown(el) {
  paintGradeNodes(el);
  paintGradeNodes(el.shadowRoot);
  const inner = el.shadowRoot && el.shadowRoot.querySelector("ha-markdown-element");
  if (inner && inner !== el) paintMarkdown(inner);
}

wrapUpdated("ha-more-info-info", paint, "__campusParentSched");
wrapUpdated("ha-markdown", paintMarkdown, "__campusParentGrades");
wrapUpdated("ha-markdown-element", paintMarkdown, "__campusParentGrades");
