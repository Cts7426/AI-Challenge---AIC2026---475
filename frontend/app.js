// frontend/app.js — logic search + điều hướng bàn phím (Task 3.1)
//
// Nguyên tắc: MỌI thao tác làm được không rời bàn phím —
//   / focus ô search → gõ → Enter search → mũi tên chọn → Enter phóng to
//   → Esc đóng → c copy keyframe_id (dùng khi submit).
// Chuột vẫn dùng được (click = chọn + phóng to) nhưng là đường phụ.

const $ = (id) => document.getElementById(id);
const grid = $("grid"), q = $("q"), qEn = $("q-en"), statusEl = $("status");
const lightbox = $("lightbox"), lbImg = $("lightbox-img"), lbInfo = $("lightbox-info");

let hits = [];         // kết quả hiện tại
let sel = -1;          // index ô đang chọn (con trỏ duyệt — xanh dương)
let lightboxOpen = false;

// Đánh dấu để NỘP (xanh lá) — tách khỏi con trỏ duyệt.
// KIS: tối đa 1; AVS: nhiều, GIỮ THỨ TỰ đánh dấu (thứ tự nộp có thể tính điểm).
let mode = "KIS";
let marked = [];       // list keyframe_id theo thứ tự đánh dấu
const modeBtn = $("mode-btn"), submitBtn = $("submit-btn");

// ---------------------------------------------------------------- placeholder
// Chưa có ảnh keyframe thật của BTC → thumbnail 404. Thay vì ô vỡ xấu xí,
// vẽ SVG placeholder: màu theo video_id (cùng video cùng màu — nhìn lưới là
// thấy cụm), chữ = keyframe_id. Có ảnh thật thì img load bình thường, không đụng code.
function placeholder(hit) {
  let h = 0;
  for (const ch of hit.video_id) h = (h * 31 + ch.charCodeAt(0)) % 360;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">
    <rect width="100%" height="100%" fill="hsl(${h},45%,28%)"/>
    <text x="50%" y="46%" fill="hsl(${h},70%,80%)" font-size="20" font-family="monospace"
          text-anchor="middle">${hit.keyframe_id}</text>
    <text x="50%" y="66%" fill="hsl(${h},40%,65%)" font-size="13" font-family="monospace"
          text-anchor="middle">(chưa có ảnh BTC)</text></svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

const fmtTime = (ms) =>
  ms == null ? "?" : `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

// ---------------------------------------------------------------------- search
async function search() {
  const query = q.value.trim();
  if (!query) return;
  statusEl.textContent = "Đang tìm…";
  statusEl.classList.remove("error");
  const t0 = performance.now();
  try {
    const res = await fetch("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: 50, query_en: qEn.value.trim() || null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    hits = await res.json();
    // Đo và HIỂN THỊ độ trễ — cuộc thi trừ điểm theo thời gian, phải luôn nhìn thấy số này
    statusEl.textContent = `${hits.length} kết quả · ${Math.round(performance.now() - t0)} ms`;
    marked = [];               // kết quả mới = ván mới, dấu cũ trỏ vào ảnh đã biến mất
    render();
    updateMarkUI();
    select(hits.length ? 0 : -1);
    grid.focus();
  } catch (e) {
    statusEl.textContent = e.message;
    statusEl.classList.add("error");
  }
}

function render() {
  grid.innerHTML = "";
  hits.forEach((hit, i) => {
    const card = document.createElement("figure");
    card.className = "card";
    card.dataset.i = i;
    const img = document.createElement("img");
    // KHÔNG dùng loading="lazy": lazy dựa vào intersection/compositor — môi
    // trường webview treo compositor là ảnh kẹt "pending" vĩnh viễn, onerror
    // không bao giờ chạy. 50 thumbnail tải thẳng vừa rẻ vừa đoán được.
    // onerror gắn TRƯỚC khi gán src — không để hở khe lỡ mất sự kiện lỗi.
    img.onerror = () => { img.onerror = null; img.src = placeholder(hit); };
    img.src = hit.thumbnail_url;
    const cap = document.createElement("figcaption");
    cap.innerHTML = `<span class="kf">${hit.keyframe_id} · ${fmtTime(hit.timestamp_ms)}</span>
                     <span class="score">${hit.score.toFixed(2)}</span>`;
    const badge = document.createElement("span");
    badge.className = "badge";
    card.append(badge, img, cap);
    // Click thường = xem; Ctrl+click = đánh dấu nộp (đường chuột của phím Space)
    card.onclick = (e) => {
      select(i);
      e.ctrlKey ? toggleMark(i) : openLightbox();
    };
    grid.append(card);
  });
}

// ------------------------------------------------------------------ mark/submit
function toggleMark(i) {
  if (i < 0) return;
  const kf = hits[i].keyframe_id;
  if (mode === "KIS") {
    // KIS chỉ nộp 1: dấu mới THAY dấu cũ (bấm lại chính nó = bỏ dấu)
    marked = marked[0] === kf ? [] : [kf];
  } else {
    const at = marked.indexOf(kf);
    at >= 0 ? marked.splice(at, 1) : marked.push(kf);
  }
  updateMarkUI();
}

function updateMarkUI() {
  [...grid.children].forEach((card, i) => {
    const at = marked.indexOf(hits[i].keyframe_id);
    card.classList.toggle("marked", at >= 0);
    // AVS: badge đánh số thứ tự nộp; KIS: dấu ✓
    card.querySelector(".badge").textContent = mode === "AVS" ? at + 1 : "✓";
  });
  submitBtn.textContent = `Nộp (${marked.length})`;
  submitBtn.disabled = marked.length === 0;
  modeBtn.textContent = mode;
  modeBtn.classList.toggle("avs", mode === "AVS");
}

function toggleMode() {
  mode = mode === "KIS" ? "AVS" : "KIS";
  if (mode === "KIS" && marked.length > 1) marked = [marked[0]]; // KIS chỉ giữ dấu đầu
  updateMarkUI();
}
modeBtn.onclick = toggleMode;

async function submit() {
  if (!marked.length) { toast("Chưa đánh dấu keyframe nào (phím Space)"); return; }
  const items = marked.map((kf) => {
    const h = hits.find((x) => x.keyframe_id === kf);
    return { keyframe_id: h.keyframe_id, video_id: h.video_id, timestamp_ms: h.timestamp_ms };
  });
  try {
    const res = await fetch("/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_type: mode, items }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    toast(`Đã nộp ${items.length} → ${data.file}`);
  } catch (e) {
    toast(`Lỗi nộp: ${e.message}`);
  }
}
submitBtn.onclick = submit;

// ------------------------------------------------------------------- selection
function select(i) {
  if (sel >= 0) grid.children[sel]?.classList.remove("selected");
  sel = i;
  if (sel < 0) return;
  const card = grid.children[sel];
  card.classList.add("selected");
  card.scrollIntoView({ block: "nearest" });   // giữ ô chọn luôn trong tầm mắt
  if (lightboxOpen) openLightbox();            // đang phóng to thì ←/→ thay ảnh luôn
}

// Số cột thực tế của grid (responsive) — đo bằng offsetTop thay vì đoán CSS:
// đếm bao nhiêu ô nằm cùng hàng đầu tiên. Đúng với mọi cỡ màn hình.
function columns() {
  if (grid.children.length < 2) return 1;
  const top0 = grid.children[0].offsetTop;
  let n = 1;
  while (n < grid.children.length && grid.children[n].offsetTop === top0) n++;
  return n;
}

// -------------------------------------------------------------------- lightbox
function openLightbox() {
  if (sel < 0) return;
  const hit = hits[sel];
  lbImg.src = grid.children[sel].querySelector("img").src; // tái dùng ảnh/placeholder đã có
  lbInfo.innerHTML = `<b>${hit.keyframe_id}</b> · video ${hit.video_id} ·
                      t=${fmtTime(hit.timestamp_ms)} · score ${hit.score.toFixed(3)}`;
  lightbox.hidden = false;
  lightboxOpen = true;
}
function closeLightbox() { lightbox.hidden = true; lightboxOpen = false; }
lightbox.onclick = closeLightbox;

// ---------------------------------------------------------------------- toast
function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.append(t);
  setTimeout(() => t.remove(), 1400);
}

// ------------------------------------------------------------------- keyboard
$("search-form").onsubmit = (e) => { e.preventDefault(); search(); };

document.addEventListener("keydown", (e) => {
  const typing = e.target === q || e.target === qEn;

  if (e.key === "Escape") {
    if (lightboxOpen) closeLightbox();
    else if (typing) e.target.blur();
    return;
  }
  if (typing) return;               // đang gõ query — nhường phím cho ô input

  if (e.key === "/") { e.preventDefault(); q.focus(); q.select(); return; }
  if (!hits.length) return;

  const col = columns();
  const move = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: col, ArrowUp: -col }[e.key];
  if (move !== undefined) {
    e.preventDefault();
    select(Math.max(0, Math.min(hits.length - 1, (sel < 0 ? 0 : sel + move))));
  } else if (e.key === "Enter") {
    e.preventDefault();
    lightboxOpen ? closeLightbox() : openLightbox();
  } else if (e.key === " ") {
    e.preventDefault();               // chặn page-scroll mặc định của Space
    toggleMark(sel);
  } else if (e.key === "m") {
    toggleMode();
  } else if (e.key === "s") {
    submit();
  } else if (e.key === "c" && sel >= 0) {
    navigator.clipboard.writeText(hits[sel].keyframe_id)
      .then(() => toast(`Đã copy ${hits[sel].keyframe_id}`));
  }
});
