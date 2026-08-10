const statusLabels = window.__STATUS_LABELS__ || {};
const activeView = window.__ACTIVE_VIEW__ || "student";

const state = {
  student: null,
  admin: null,
  studentId: 1,
  adminId: 2,
  activeFilter: "",
  currentRequest: null,
};

const els = {
  body: document.body,
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  studentStatus: document.getElementById("student-status"),
  studentMeta: document.getElementById("student-meta"),
  adminStatus: document.getElementById("admin-status"),
  adminMeta: document.getElementById("admin-meta"),
  studentLogin: document.getElementById("student-login"),
  adminLogin: document.getElementById("admin-login"),
  studentUsername: document.getElementById("student-username"),
  studentPassword: document.getElementById("student-password"),
  adminUsername: document.getElementById("admin-username"),
  adminPassword: document.getElementById("admin-password"),
  requestTable: document.getElementById("request-table"),
  requestDetail: document.getElementById("request-detail"),
  requestHistory: document.getElementById("request-history"),
  countPending: document.getElementById("count-pending"),
  countApproved: document.getElementById("count-approved"),
  countRejected: document.getElementById("count-rejected"),
  countCancelled: document.getElementById("count-cancelled"),
};

function setActivePanel(panelId) {
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === panelId);
  });
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tabTarget === panelId);
  });
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function addChatBubble(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.innerHTML = `<div class="chat-meta">${role === "user" ? "Sinh viên" : role === "bot" ? "Bot" : "Hệ thống"}</div>${escapeHtml(content).replace(/\n/g, "<br>")}`;
  els.chatLog.appendChild(bubble);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function renderStatusCounts(counts) {
  els.countPending.textContent = counts.PENDING ?? 0;
  els.countApproved.textContent = counts.APPROVED ?? 0;
  els.countRejected.textContent = counts.REJECTED ?? 0;
  els.countCancelled.textContent = counts.CANCELLED ?? 0;
}

function renderRequests(requests) {
  els.requestTable.innerHTML = requests.map((request) => {
    const status = request.status || "PENDING";
    const statusLabel = statusLabels[status] || status;
    return `
      <tr>
        <td>#${request.id}</td>
        <td>${escapeHtml(request.student_name || request.student_username || request.student_id || "-")}</td>
        <td>${escapeHtml(request.course_code || "-")}</td>
        <td>${escapeHtml(request.class_code || "-")}</td>
        <td>${escapeHtml(request.start_date || "-")} → ${escapeHtml(request.end_date || "-")}</td>
        <td><span class="status-tag ${status}">${escapeHtml(statusLabel)}</span></td>
        <td>
          <div class="action-group">
            <button class="small-btn approve" data-action="approve" data-id="${request.id}">Duyệt</button>
            <button class="small-btn reject" data-action="reject" data-id="${request.id}">Từ chối</button>
            <button class="small-btn cancel" data-action="cancel" data-id="${request.id}">Huỷ</button>
            <button class="chip" data-action="detail" data-id="${request.id}">Chi tiết</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function fetchAdminData() {
  const url = new URL("/api/admin/requests", window.location.origin);
  if (state.activeFilter) {
    url.searchParams.set("status", state.activeFilter);
  }
  const response = await fetch(url);
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.message || "Không tải được dữ liệu quản lý.");
  renderStatusCounts(payload.data.status_counts || {});
  renderRequests(payload.data.requests || []);
}

async function refreshStudentRequests() {
  const response = await fetch(`/api/student/requests?student_id=${state.studentId}`);
  const payload = await response.json();
  if (!payload.ok) return;
}

function appendSystemMessage(text) {
  addChatBubble("system", text);
}

async function sendChatMessage(message) {
  if (!state.student) {
    appendSystemMessage("Hãy đăng nhập mô phỏng sinh viên trước khi chat.");
    return;
  }
  addChatBubble("user", message);
  els.chatInput.value = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sender: state.student.username,
        message,
        metadata: { student_id: state.student.id, username: state.student.username },
      }),
    });
    const payload = await response.json();
    if (!payload.ok) {
      appendSystemMessage(payload.message || "Không gửi được tin nhắn.");
      return;
    }
    const botMessages = payload.data || [];
    if (!botMessages.length) {
      appendSystemMessage("Bot chưa trả lời.");
      return;
    }
    botMessages.forEach((item) => addChatBubble("bot", item.text || JSON.stringify(item)));
  } catch (error) {
    appendSystemMessage(error.message);
  }
}

async function loginUser(role) {
  const username = document.getElementById(`${role}-username`).value.trim();
  const password = document.getElementById(`${role}-password`).value;
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.message || "Đăng nhập thất bại");
  return payload.data;
}

async function handleStudentLogin() {
  try {
    state.student = await loginUser("student");
    state.studentId = state.student.id;
    els.studentStatus.textContent = `Sinh viên: ${state.student.full_name} (${state.student.username})`;
    els.studentMeta.textContent = `Role: ${state.student.role} | Lớp: ${state.student.class_code || "-"}`;
    appendSystemMessage(`Đăng nhập thành công: ${state.student.full_name}`);
    await refreshStudentRequests();
  } catch (error) {
    appendSystemMessage(error.message);
  }
}

async function handleAdminLogin() {
  try {
    state.admin = await loginUser("admin");
    state.adminId = state.admin.id;
    els.adminStatus.textContent = `Giáo vụ: ${state.admin.full_name} (${state.admin.username})`;
    els.adminMeta.textContent = `Role: ${state.admin.role} | Quản lý trạng thái đơn`;
    await fetchAdminData();
  } catch (error) {
    appendSystemMessage(error.message);
  }
}

async function updateRequest(requestId, action) {
  const endpointMap = {
    approve: `/api/admin/requests/${requestId}/approve`,
    reject: `/api/admin/requests/${requestId}/reject`,
    cancel: `/api/admin/requests/${requestId}/cancel`,
  };
  const response = await fetch(endpointMap[action], {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ admin_id: state.admin ? state.admin.id : 2 }),
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.message || "Không thể cập nhật trạng thái.");
  await fetchAdminData();
  await refreshDetail(requestId);
}

async function refreshDetail(requestId) {
  const response = await fetch(`/api/admin/requests/${requestId}`);
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.message || "Không tải được chi tiết.");
  state.currentRequest = payload.data;
  const detail = payload.data;
  els.requestDetail.textContent = JSON.stringify(detail, null, 2);
  els.requestHistory.textContent = JSON.stringify(detail.history || [], null, 2);
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => setActivePanel(button.dataset.tabTarget));
  });

  document.querySelectorAll(".filter-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelectorAll(".filter-btn").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      state.activeFilter = button.dataset.filter || "";
      await fetchAdminData();
    });
  });

  document.querySelectorAll(".chip[data-msg]").forEach((button) => {
    button.addEventListener("click", () => {
      setActivePanel("student-panel");
      els.chatInput.value = button.dataset.msg;
      els.chatInput.focus();
    });
  });

  els.studentLogin.addEventListener("click", handleStudentLogin);
  els.adminLogin.addEventListener("click", handleAdminLogin);

  els.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = els.chatInput.value.trim();
    if (!message) return;
    await sendChatMessage(message);
  });

  els.requestTable.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const requestId = Number(button.dataset.id);
    const action = button.dataset.action;
    try {
      if (action === "detail") {
        await refreshDetail(requestId);
        return;
      }
      await updateRequest(requestId, action);
    } catch (error) {
      appendSystemMessage(error.message);
    }
  });
}

function seedSystemMessages() {
  addChatBubble("system", "Chào mừng bạn đến với chatbot chuyên cần. Hãy đăng nhập mô phỏng rồi thử nhắn: em muốn xin nghỉ học.");
  const counts = window.__STATUS_COUNTS__ || {};
  renderStatusCounts(counts);
}

function boot() {
  bindEvents();
  seedSystemMessages();
  setActivePanel(activeView === "admin" ? "admin-panel" : "student-panel");
  fetchAdminData().catch(() => {});
}

boot();
