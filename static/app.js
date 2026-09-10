// Global State & Definitions
const statusLabels = window.__STATUS_LABELS__ || {
  PENDING: "Chờ duyệt",
  APPROVED: "Đã duyệt",
  REJECTED: "Từ chối",
  CANCELLED: "Đã Huỷ",
};

const state = {
  currentUser: null,
  activeFilter: "",
  currentRequestId: null,
  rejectTargetId: null,
  editTargetId: null,
  sseSource: null,
};

// DOM References
const els = {
  // Toast container
  toastContainer: document.getElementById("toast-container"),

  // Header & Auth
  topbarActions: document.getElementById("topbar-actions"),
  userBadge: document.getElementById("user-badge"),
  userAvatarIcon: document.getElementById("user-avatar-icon"),
  userDisplayName: document.getElementById("user-display-name"),
  userDisplayRole: document.getElementById("user-display-role"),
  logoutBtn: document.getElementById("logout-btn"),
  tabBtnStudent: document.getElementById("tab-btn-student"),
  tabBtnAdmin: document.getElementById("tab-btn-admin"),

  // Login Panel
  loginPanel: document.getElementById("login-panel"),
  btnSelectStudent: document.getElementById("btn-select-student"),
  btnSelectStaff: document.getElementById("btn-select-staff"),
  loginStudentBlock: document.getElementById("login-student-block"),
  loginStaffBlock: document.getElementById("login-staff-block"),
  studentLoginForm: document.getElementById("student-login-form"),
  staffLoginForm: document.getElementById("staff-login-form"),
  studentUsernameInput: document.getElementById("student-username"),
  studentPasswordInput: document.getElementById("student-password"),
  adminUsernameInput: document.getElementById("admin-username"),
  adminPasswordInput: document.getElementById("admin-password"),
  studentLoginBtn: document.getElementById("student-login-btn"),
  adminLoginBtn: document.getElementById("admin-login-btn"),

  // Panels
  studentPanel: document.getElementById("student-panel"),
  adminPanel: document.getElementById("admin-panel"),

  // Student Form & Inputs
  createRequestForm: document.getElementById("create-request-form"),
  formCourseCode: document.getElementById("form-course-code"),
  formClassCode: document.getElementById("form-class-code"),
  formStartDate: document.getElementById("form-start-date"),
  formEndDate: document.getElementById("form-end-date"),
  formReason: document.getElementById("form-reason"),
  formEvidenceUrl: document.getElementById("form-evidence-url"),
  dateErrorMsg: document.getElementById("date-error-msg"),
  formSubmitBtn: document.getElementById("form-submit-btn"),
  formCancelBtn: document.getElementById("form-cancel-btn"),

  // Student Views
  btnSubMyRequests: document.getElementById("btn-sub-my-requests"),
  btnSubChat: document.getElementById("btn-sub-chat"),
  btnSubForm: document.getElementById("btn-sub-form"), // ← THÊM DÒNG NÀY
  studentMyRequestsView: document.getElementById("student-my-requests-view"),
  studentChatView: document.getElementById("student-chat-view"),
  studentRequestTable: document.getElementById("student-request-table"),
  studentFormView: document.getElementById("student-form-view"), // ← nên thêm luôn

  // Chat
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),

  // Admin Panel
  countAll: document.getElementById("count-all"),
  countPending: document.getElementById("count-pending"),
  countApproved: document.getElementById("count-approved"),
  countRejected: document.getElementById("count-rejected"),
  countCancelled: document.getElementById("count-cancelled"),
  requestTable: document.getElementById("request-table"),

  // Modals
  detailModal: document.getElementById("detail-modal"),
  closeDetailModalBtn: document.getElementById("close-detail-modal-btn"),
  btnCloseDetailModal: document.getElementById("btn-close-detail-modal"),
  modalDetailTitle: document.getElementById("modal-detail-title"),
  detailStatusBanner: document.getElementById("detail-status-banner"),
  detailStatusText: document.getElementById("detail-status-text"),
  detailResultDesc: document.getElementById("detail-result-desc"),
  detailStudentName: document.getElementById("detail-student-name"),
  detailStudentMeta: document.getElementById("detail-student-meta"),
  detailCourse: document.getElementById("detail-course"),
  detailDates: document.getElementById("detail-dates"),
  detailReason: document.getElementById("detail-reason"),
  detailHandlerWrap: document.getElementById("detail-handler-wrap"),
  detailHandlerInfo: document.getElementById("detail-handler-info"),
  detailEvidencesList: document.getElementById("detail-evidences-list"),
  detailHistoryTimeline: document.getElementById("detail-history-timeline"),

  // Reject Modal
  rejectModal: document.getElementById("reject-modal"),
  closeRejectModalBtn: document.getElementById("close-reject-modal-btn"),
  rejectReasonInput: document.getElementById("reject-reason-input"),
  confirmRejectBtn: document.getElementById("confirm-reject-btn"),
  cancelRejectBtn: document.getElementById("cancel-reject-btn"),

  // Edit Modal (Adjustment of Staff Decision)
  editModal: document.getElementById("edit-modal"),
  closeEditModalBtn: document.getElementById("close-edit-modal-btn"),
  editSummaryStudent: document.getElementById("edit-summary-student"),
  editSummaryCourse: document.getElementById("edit-summary-course"),
  editSummaryDates: document.getElementById("edit-summary-dates"),
  editTargetStatus: document.getElementById("edit-target-status"),
  editNoteInput: document.getElementById("edit-note-input"),
  confirmEditBtn: document.getElementById("confirm-edit-btn"),
  cancelEditBtn: document.getElementById("cancel-edit-btn"),
};

// =====================================================
// Hàm chuyển tab dành cho Sinh viên
// =====================================================
function switchStudentTab(tab) {
  const btnSubChat = document.getElementById("btn-sub-chat");
  const btnSubMyRequests = document.getElementById("btn-sub-my-requests");
  const btnSubForm = document.getElementById("btn-sub-form");

  const chatView = document.getElementById("student-chat-view");
  const requestsView = document.getElementById("student-my-requests-view");
  const formView = document.getElementById("student-form-view");

  // Reset tất cả
  if (btnSubChat) btnSubChat.classList.remove("is-active");
  if (btnSubMyRequests) btnSubMyRequests.classList.remove("is-active");
  if (btnSubForm) btnSubForm.classList.remove("is-active");

  if (chatView) chatView.style.display = "none";
  if (requestsView) requestsView.style.display = "none";
  if (formView) formView.style.display = "none";

  if (tab === "chat") {
    if (btnSubChat) btnSubChat.classList.add("is-active");
    if (chatView) chatView.style.display = "block";
  } else if (tab === "requests") {
    if (btnSubMyRequests) btnSubMyRequests.classList.add("is-active");
    if (requestsView) requestsView.style.display = "block";
  } else if (tab === "form") {
    if (btnSubForm) btnSubForm.classList.add("is-active");
    if (formView) formView.style.display = "block";
  }
}
// Utilities
function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDateDisplay(dateStr) {
  if (!dateStr) return "-";
  const s = String(dateStr).strip ? String(dateStr).strip() : String(dateStr);
  const parts = s.split("-");
  if (parts.length === 3 && parts[0].length === 4) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return dateStr;
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast-msg toast-${type}`;
  let icon = "ℹ️";
  if (type === "success") icon = "✅";
  if (type === "error") icon = "❌";
  if (type === "warning") icon = "⚠️";
  toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
  els.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ----------------------------------------------------
// REQUIREMENT 1: Real-time Date Validation
// ----------------------------------------------------
function validateFormDates() {
  const startVal = els.formStartDate.value;
  const endVal = els.formEndDate.value;

  if (startVal && endVal) {
    const dStart = new Date(startVal);
    const dEnd = new Date(endVal);

    if (dStart > dEnd) {
      // Hiển thị lỗi ngay lập tức
      els.dateErrorMsg.style.display = "block";
      els.dateErrorMsg.textContent =
        "⚠️ Ngày kết thúc không được trước ngày bắt đầu.";
      els.formEndDate.classList.add("has-error");
      els.formSubmitBtn.disabled = true;
      els.formSubmitBtn.classList.add("disabled");
      return false;
    }
  }

  // Hợp lệ -> Ẩn lỗi
  els.dateErrorMsg.style.display = "none";
  els.formEndDate.classList.remove("has-error");
  els.formSubmitBtn.disabled = false;
  els.formSubmitBtn.classList.remove("disabled");
  return true;
}

// ----------------------------------------------------
// REQUIREMENT 2: Authentication & Authorization Flow
// ----------------------------------------------------
async function checkAuthSession() {
  try {
    const res = await fetch("/api/auth/me");
    const payload = await res.json();
    if (payload.ok && payload.data) {
      state.currentUser = payload.data;
      renderAuthenticatedUI();
    } else {
      state.currentUser = null;
      renderUnauthenticatedUI();
    }
  } catch (err) {
    state.currentUser = null;
    renderUnauthenticatedUI();
  }
}

function renderUnauthenticatedUI() {
  // Ẩn các trang chức năng
  els.studentPanel.style.display = "none";
  els.adminPanel.style.display = "none";
  els.topbarActions.style.display = "none";
  els.userBadge.style.display = "none";

  // Hiển thị Form Đăng Nhập
  els.loginPanel.style.display = "block";
  // Xóa chat log khi đăng xuất / chưa đăng nhập
  if (els.chatLog) {
    els.chatLog.innerHTML = "";
  }
  document.getElementById("app-subtitle").textContent =
    "Bắt buộc đăng nhập để xem thông tin và sử dụng các chức năng hệ thống.";

  // Xoá nội dung dữ liệu nhạy cảm
  els.studentRequestTable.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Vui lòng đăng nhập trước</td></tr>`;
  els.requestTable.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Vui lòng đăng nhập trước</td></tr>`;

  if (state.sseSource) {
    state.sseSource.close();
    state.sseSource = null;
  }
}

function renderAuthenticatedUI() {
  const user = state.currentUser;
  if (!user) return renderUnauthenticatedUI();

  // Hiển thị thông tin phiên đăng nhập ở Header
  els.loginPanel.style.display = "none";
  els.userBadge.style.display = "flex";
  els.userAvatarIcon.textContent = user.role === "STUDENT" ? "🎓" : "👨‍🏫";
  els.userDisplayName.textContent = `${user.full_name} (${user.username})`;
  els.userDisplayRole.textContent =
    user.role === "STUDENT" ? "Sinh viên" : "Giáo vụ";

  document.getElementById("app-subtitle").textContent =
    user.role === "STUDENT"
      ? `Xin chào sinh viên ${user.full_name}. Bạn có thể tạo đơn xin nghỉ và theo dõi kết quả tại đây.`
      : `Xin chào giáo vụ ${user.full_name}. Bảng điều khiển quản lý và phê duyệt đơn xin nghỉ học.`;

  // Phân quyền hiển thị theo Role
  if (user.role === "STUDENT") {
    els.topbarActions.style.display = "none";
    els.studentPanel.style.display = "block";
    els.adminPanel.style.display = "none";
    // Reset Rasa khi load lại trang
    fetch("/api/chat/restart", { method: "POST" }).catch(() => {});
    // Tự điền mặc định lớp của sinh viên nếu có
    if (user.class_code && !els.formClassCode.value) {
      els.formClassCode.value = user.class_code;
    }
    fetchStudentRequests();
    // Xóa sạch chat cũ mỗi lần đăng nhập / load lại
    if (els.chatLog) {
      els.chatLog.innerHTML = "";
      addChatBubble(
        "system",
        "Xin chào! Bạn cần hỗ trợ xin nghỉ học hay tra cứu quy định vắng học?",
      );
    }
    // Mặc định mở tab Chatbot
    switchStudentTab("chat");
  } else if (user.role === "STAFF") {
    els.topbarActions.style.display = "none";
    els.studentPanel.style.display = "none";
    els.adminPanel.style.display = "block";
    fetchAdminData();
  }

  // Bật kết nối Realtime SSE
  initRealtimeSSE();
}

async function handleLogin(username, password) {
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const payload = await res.json();
    if (!payload.ok) {
      showToast(payload.message || "Đăng nhập thất bại", "error");
      return;
    }

    state.currentUser = payload.data;
    showToast(`Đăng nhập thành công!`, "success");

    // Xóa sạch chat log trước khi hiện giao diện mới
    if (els.chatLog) {
      els.chatLog.innerHTML = "";
      addChatBubble(
        "system",
        "Xin chào! Bạn cần hỗ trợ xin nghỉ học hay tra cứu quy định vắng học?",
      );
    }
    // Reset hội thoại Rasa
    try {
      await fetch("/api/chat/restart", { method: "POST" });
    } catch (e) {
      console.warn("Không reset được chatbot:", e);
    }

    renderAuthenticatedUI();
  } catch (err) {
    console.error("Login error:", err);
    showToast("Lỗi kết nối máy chủ", "error");
  }
}

async function handleLogout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (e) {}
  state.currentUser = null;
  showToast("Đã đăng xuất thành công", "info");
  renderUnauthenticatedUI();
}

// ----------------------------------------------------
// REQUIREMENT 3: Clear UI Feedback & Real-Time Sync
// ----------------------------------------------------
function initRealtimeSSE() {
  if (state.sseSource) return;
  try {
    const sse = new EventSource("/api/events");
    sse.addEventListener("request_created", () => {
      if (state.currentUser?.role === "STAFF") fetchAdminData();
      if (state.currentUser?.role === "STUDENT") fetchStudentRequests();
    });
    sse.addEventListener("request_updated", (e) => {
      const data = JSON.parse(e.data || "{}");
      if (state.currentUser?.role === "STAFF") fetchAdminData();
      if (state.currentUser?.role === "STUDENT") fetchStudentRequests();
      if (
        state.currentRequestId &&
        data.request_id === state.currentRequestId
      ) {
        refreshDetailModal(state.currentRequestId);
      }
    });
    state.sseSource = sse;
  } catch (err) {}
}

// ----------------------------------------------------
// Student Actions (Submit, Cancel Draft, Cancel Request)
// ----------------------------------------------------
async function handleCreateRequestSubmit(e) {
  e.preventDefault();
  if (!validateFormDates()) {
    showToast("Ngày kết thúc không được trước ngày bắt đầu.", "error");
    return;
  }

  const course_code = els.formCourseCode.value.trim();
  const class_code = els.formClassCode.value.trim();
  const start_date = els.formStartDate.value;
  const end_date = els.formEndDate.value;
  const reason = els.formReason.value.trim();
  const evidence_url = els.formEvidenceUrl.value.trim();

  if (!course_code || !class_code || !start_date || !end_date || !reason) {
    showToast("Vui lòng nhập đầy đủ các thông tin bắt buộc.", "warning");
    return;
  }

  // Loading state
  els.formSubmitBtn.disabled = true;
  els.formSubmitBtn.textContent = "Đang gửi đơn...";

  try {
    const res = await fetch("/api/student/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        course_code,
        class_code,
        start_date,
        end_date,
        reason,
        evidence_url,
      }),
    });
    const payload = await res.json();
    if (!payload.ok) {
      showToast(
        payload.message || "Gửi đơn thất bại. Vui lòng thử lại.",
        "error",
      );
      return;
    }

    showToast("Gửi đơn thành công.", "success");
    // Reset form
    els.createRequestForm.reset();
    validateFormDates();
    fetchStudentRequests();
  } catch (err) {
    showToast("Gửi đơn thất bại. Vui lòng thử lại.", "error");
  } finally {
    els.formSubmitBtn.disabled = false;
    els.formSubmitBtn.textContent = "Gửi Đơn Xin Nghỉ";
  }
}

// REQUIREMENT 7: Huỷ quá trình viết đơn
async function handleCancelDraft() {
  if (!confirm("Bạn có chắc muốn huỷ quá trình viết đơn không?")) {
    return;
  }

  // Reset toàn bộ input & state
  els.createRequestForm.reset();
  validateFormDates();
  localStorage.removeItem("draft_absence_request");
  sessionStorage.removeItem("draft_absence_request");

  try {
    await fetch("/api/student/reset-draft", { method: "POST" });
  } catch (e) {}

  showToast("Đã huỷ quá trình viết đơn.", "info");
}

async function fetchStudentRequests() {
  try {
    const res = await fetch("/api/student/requests");
    const payload = await res.json();
    if (!payload.ok) return;

    const requests = payload.data.requests || [];
    renderStudentRequestsTable(requests);
  } catch (err) {}
}

function renderStudentRequestsTable(requests) {
  if (!requests.length) {
    els.studentRequestTable.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Bạn chưa có đơn xin nghỉ nào</td></tr>`;
    return;
  }

  els.studentRequestTable.innerHTML = requests
    .map((r) => {
      const status = r.status || "PENDING";
      const statusLabel = statusLabels[status] || status;
      const isPending = status === "PENDING";

      return `
      <tr>
        <td><b>#${r.id}</b></td>
        <td>${escapeHtml(r.course_code)}</td>
        <td>${escapeHtml(r.class_code)}</td>
        <td>${formatDateDisplay(r.start_date)} → ${formatDateDisplay(r.end_date)}</td>
        <td><span class="status-tag ${status}">${escapeHtml(statusLabel)}</span></td>
        <td>
          <div class="action-group">
            <button class="small-btn detail" onclick="openDetailModal(${r.id})">Chi tiết</button>
            ${isPending ? `<button class="small-btn cancel" onclick="handleCancelStudentRequest(${r.id})">Huỷ đơn</button>` : ""}
          </div>
        </td>
      </tr>
    `;
    })
    .join("");
}

async function handleCancelStudentRequest(requestId) {
  if (!confirm(`Bạn có chắc chắn muốn huỷ đơn #${requestId} không?`)) return;

  try {
    const res = await fetch(`/api/student/requests/${requestId}/cancel`, {
      method: "POST",
    });
    const payload = await res.json();
    if (!payload.ok) {
      showToast(payload.message || "Không thể huỷ đơn.", "error");
      return;
    }
    showToast("Đã huỷ đơn thành công.", "success");
    fetchStudentRequests();
  } catch (err) {
    showToast("Không thể huỷ đơn.", "error");
  }
}

// ----------------------------------------------------
// Admin Management Actions (Approve, Reject, Edit, Filter)
// ----------------------------------------------------
async function fetchAdminData() {
  try {
    const url = new URL("/api/admin/requests", window.location.origin);
    if (state.activeFilter) url.searchParams.set("status", state.activeFilter);

    const res = await fetch(url);
    const payload = await res.json();
    if (!payload.ok) return;

    renderStatusCounts(payload.data.status_counts || {});
    renderAdminTable(payload.data.requests || []);
  } catch (err) {}
}

function renderStatusCounts(counts) {
  const pending = counts.PENDING || 0;
  const approved = counts.APPROVED || 0;
  const rejected = counts.REJECTED || 0;
  const cancelled = counts.CANCELLED || 0;
  const total = pending + approved + rejected + cancelled;

  els.countAll.textContent = total;
  els.countPending.textContent = pending;
  els.countApproved.textContent = approved;
  els.countRejected.textContent = rejected;
  els.countCancelled.textContent = cancelled;
}

function renderAdminTable(requests) {
  if (!requests.length) {
    els.requestTable.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Không có đơn xin nghỉ nào trong mục này</td></tr>`;
    return;
  }

  els.requestTable.innerHTML = requests
    .map((r) => {
      const status = r.status || "PENDING";
      const statusLabel = statusLabels[status] || status;
      const studentName =
        r.student_name || r.student_username || `SV #${r.student_id}`;

      let actionButtons = "";
      if (status === "PENDING") {
        actionButtons = `
          <button class="small-btn approve" onclick="handleApproveRequest(${r.id}, this)">Duyệt</button>
          <button class="small-btn reject" onclick="openRejectModal(${r.id})">Từ chối</button>
          <button class="small-btn detail" onclick="openDetailModal(${r.id})">Chi tiết</button>
        `;
      } else if (status === "APPROVED" || status === "REJECTED") {
        // Kiểm tra ngày nghỉ đã quá hạn chưa
        const today = new Date();
        today.setHours(0, 0, 0, 0); // chỉ so sánh ngày, bỏ giờ

        const endDate = r.end_date ? new Date(r.end_date) : null;
        const isExpired = endDate && endDate < today;

        actionButtons = `
    <button class="small-btn detail" onclick="openDetailModal(${r.id})">Chi tiết</button>
    ${!isExpired ? `<button class="small-btn edit" onclick="openEditModal(${r.id})">Chỉnh sửa</button>` : ""}
  `;
      } else {
        actionButtons = `
          <button class="small-btn detail" onclick="openDetailModal(${r.id})">Chi tiết</button>
        `;
      }

      return `
      <tr>
        <td><b>#${r.id}</b></td>
        <td><b>${escapeHtml(studentName)}</b></td>
        <td>${escapeHtml(r.course_code)}</td>
        <td>${escapeHtml(r.class_code)}</td>
        <td>${formatDateDisplay(r.start_date)} → ${formatDateDisplay(r.end_date)}</td>
        <td><span class="status-tag ${status}">${escapeHtml(statusLabel)}</span></td>
        <td><div class="action-group">${actionButtons}</div></td>
      </tr>
    `;
    })
    .join("");
}

// Requirement 11: Race Condition Guard in Approval/Rejection
async function handleApproveRequest(requestId, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "Đang duyệt...";
  }

  try {
    const res = await fetch(`/api/admin/requests/${requestId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await res.json();

    if (!payload.ok) {
      if (res.status === 409) {
        showToast(
          payload.message || "Đơn này đã được xử lý trước đó.",
          "warning",
        );
      } else {
        showToast(payload.message || "Duyệt thất bại.", "error");
      }
      fetchAdminData();
      return;
    }

    showToast("Duyệt đơn thành công.", "success");
    fetchAdminData();
  } catch (err) {
    showToast("Duyệt thất bại.", "error");
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = "Duyệt";
    }
  }
}

function openRejectModal(requestId) {
  state.rejectTargetId = requestId;
  els.rejectReasonInput.value = "";
  els.rejectModal.style.display = "flex";
}

async function handleConfirmReject() {
  const requestId = state.rejectTargetId;
  const reason = els.rejectReasonInput.value.trim();
  if (!requestId) return;

  els.confirmRejectBtn.disabled = true;
  els.confirmRejectBtn.textContent = "Đang xử lý...";

  try {
    const res = await fetch(`/api/admin/requests/${requestId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: reason }),
    });
    const payload = await res.json();

    if (!payload.ok) {
      if (res.status === 409) {
        showToast(
          payload.message || "Đơn này đã được xử lý trước đó.",
          "warning",
        );
      } else {
        showToast(payload.message || "Từ chối đơn thất bại.", "error");
      }
      fetchAdminData();
      return;
    }

    showToast("Đã từ chối đơn.", "success");
    els.rejectModal.style.display = "none";
    fetchAdminData();
  } catch (err) {
    showToast("Từ chối đơn thất bại.", "error");
  } finally {
    els.confirmRejectBtn.disabled = false;
    els.confirmRejectBtn.textContent = "Xác Nhận Từ Chối";
  }
}

// Requirement 14: Adjust Staff Approval Decision (Duyệt / Từ chối lại)
async function openEditModal(requestId) {
  state.editTargetId = requestId;
  try {
    const res = await fetch(`/api/admin/requests/${requestId}`);
    const payload = await res.json();
    if (!payload.ok) {
      showToast("Không tìm thấy đơn.", "error");
      return;
    }

    const req = payload.data;
    const studentName =
      req.student_name || req.student_username || `SV #${req.student_id}`;

    els.editSummaryStudent.innerHTML = `<b>Sinh viên:</b> ${escapeHtml(studentName)} (${req.student_username || req.student_id})`;
    els.editSummaryCourse.innerHTML = `<b>Môn học / Lớp:</b> ${escapeHtml(req.course_code)} - ${escapeHtml(req.class_code)}`;
    els.editSummaryDates.innerHTML = `<b>Thời gian nghỉ:</b> ${formatDateDisplay(req.start_date)} đến ${formatDateDisplay(req.end_date)}`;

    els.editTargetStatus.value =
      req.status === "APPROVED" ? "REJECTED" : "APPROVED";
    els.editNoteInput.value = "";

    els.editModal.style.display = "flex";
  } catch (err) {
    showToast("Không tải được thông tin đơn.", "error");
  }
}

async function handleConfirmEdit() {
  const requestId = state.editTargetId;
  const new_status = els.editTargetStatus.value;
  const note = els.editNoteInput.value.trim();

  if (!requestId || !new_status) return;

  els.confirmEditBtn.disabled = true;
  els.confirmEditBtn.textContent = "Đang lưu...";

  try {
    const res = await fetch(`/api/admin/requests/${requestId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_status, note }),
    });
    const payload = await res.json();

    if (!payload.ok) {
      showToast(payload.message || "Đổi trạng thái đơn thất bại.", "error");
      return;
    }

    showToast(
      payload.message || "Đã điều chỉnh trạng thái đơn thành công.",
      "success",
    );
    els.editModal.style.display = "none";
    fetchAdminData();
  } catch (err) {
    showToast("Điều chỉnh trạng thái đơn thất bại.", "error");
  } finally {
    els.confirmEditBtn.disabled = false;
    els.confirmEditBtn.textContent = "Lưu Trạng Thái Mới";
  }
}

// ----------------------------------------------------
// REQUIREMENT 4 & 5: User-friendly Detail View & Timeline
// ----------------------------------------------------
async function openDetailModal(requestId) {
  state.currentRequestId = requestId;
  els.detailModal.style.display = "flex";
  refreshDetailModal(requestId);
}

async function refreshDetailModal(requestId) {
  els.modalDetailTitle.textContent = `Chi Tiết Đơn Xin Nghỉ Học #${requestId}`;
  try {
    const res = await fetch(`/api/admin/requests/${requestId}`);
    const payload = await res.json();
    if (!payload.ok) return;

    const req = payload.data;
    const status = req.status || "PENDING";

    // Setup Status Banner
    els.detailStatusBanner.className = `status-banner banner-${status.toLowerCase()}`;
    if (status === "PENDING") {
      els.detailStatusText.textContent = "Trạng thái: Chờ duyệt";
      els.detailResultDesc.textContent =
        "⏳ Đơn xin nghỉ học của bạn đang chờ giáo vụ xem xét và phê duyệt.";
    } else if (status === "APPROVED") {
      els.detailStatusText.textContent = "Trạng thái: Đã duyệt";
      els.detailResultDesc.textContent =
        "✅ Đơn xin nghỉ của bạn đã được giáo vụ duyệt.";
    } else if (status === "REJECTED") {
      els.detailStatusText.textContent = "Trạng thái: Từ chối";
      const rejectNote = req.last_note ? ` Lý do: ${req.last_note}` : "";
      els.detailResultDesc.textContent = `❌ Đơn của bạn đã bị từ chối.${rejectNote}`;
    } else if (status === "CANCELLED") {
      els.detailStatusText.textContent = "Trạng thái: Đã huỷ";
      els.detailResultDesc.textContent =
        "⚪ Đơn xin nghỉ học này đã được sinh viên huỷ.";
    }

    // Fill info grid
    els.detailStudentName.textContent =
      req.student_name || req.student_username || `SV #${req.student_id}`;
    els.detailStudentMeta.textContent = `MSSV: ${req.student_username || req.student_id} | Lớp: ${req.class_code}`;
    els.detailCourse.textContent = req.course_code;
    els.detailDates.textContent = `${formatDateDisplay(req.start_date)} đến ${formatDateDisplay(req.end_date)}`;
    els.detailReason.textContent = req.reason;

    if (req.handler_name) {
      els.detailHandlerWrap.style.display = "flex";
      els.detailHandlerInfo.textContent = `${req.handler_name} (${req.handled_at || ""})`;
    } else {
      els.detailHandlerWrap.style.display = "none";
    }

    // Render Evidences
    const evidences = req.evidences || [];
    if (evidences.length > 0) {
      els.detailEvidencesList.innerHTML = evidences
        .map(
          (ev) => `
        <div style="margin-bottom:6px;">
          🔗 <a href="${escapeHtml(ev.file_url)}" target="_blank" rel="noopener noreferrer">
            <b>${escapeHtml(ev.file_name || "Xem file minh chứng")}</b>
          </a> (${ev.uploaded_at || ""})
        </div>
      `,
        )
        .join("");
    } else {
      els.detailEvidencesList.innerHTML = `<p class="text-muted">Không có minh chứng đính kèm</p>`;
    }

    // Render Timeline History (Requirement 5)
    const history = req.history || [];
    if (history.length > 0) {
      els.detailHistoryTimeline.innerHTML = history
        .map((h) => {
          const person =
            h.changer_name || h.changer_username || `ID #${h.changed_by}`;
          const noteText =
            h.note ||
            `Chuyển trạng thái sang ${statusLabels[h.new_status] || h.new_status}`;
          return `
          <div class="timeline-item">
            <div class="timeline-time">${h.changed_at || ""}</div>
            <div class="timeline-content">${escapeHtml(noteText)}</div>
          </div>
        `;
        })
        .join("");
    } else {
      els.detailHistoryTimeline.innerHTML = `<p class="text-muted">Chưa có lịch sử trạng thái</p>`;
    }
  } catch (err) {}
}

// ----------------------------------------------------
// Chatbot Client
// ----------------------------------------------------
async function sendChatMessage(message) {
  if (!state.currentUser) {
    showToast("Hãy đăng nhập trước khi chat.", "warning");
    return;
  }
  addChatBubble("user", message);
  els.chatInput.value = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const payload = await res.json();
    if (!payload.ok) {
      addChatBubble("system", payload.message || "Không gửi được tin nhắn.");
      return;
    }
    const botMessages = payload.data || [];
    if (!botMessages.length) {
      addChatBubble("bot", "Bot chưa phản hồi.");
      return;
    }
    botMessages.forEach((msg) =>
      addChatBubble("bot", msg.text || JSON.stringify(msg)),
    );
  } catch (err) {
    addChatBubble("system", "Lỗi kết nối chatbot.");
  }
}

function addChatBubble(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  const senderLabel =
    role === "user" ? "Sinh viên" : role === "bot" ? "Bot Trợ Lý" : "Hệ thống";
  bubble.innerHTML = `<div class="chat-meta">${senderLabel}</div>${escapeHtml(content).replace(/\n/g, "<br>")}`;
  els.chatLog.appendChild(bubble);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}
// ----------------------------------------------------
// Hàm đóng modal
// ----------------------------------------------------
function closeDetailModal() {
  if (els.detailModal) els.detailModal.style.display = "none";
}

function closeRejectModal() {
  if (els.rejectModal) els.rejectModal.style.display = "none";
}

function closeEditModal() {
  if (els.editModal) els.editModal.style.display = "none";
}

// ----------------------------------------------------
// Global Event Listeners & Binding
// ----------------------------------------------------
function bindEvents() {
  // Role switcher
  if (els.btnSelectStudent) {
    els.btnSelectStudent.addEventListener("click", () => {
      els.btnSelectStudent.classList.add("is-active");
      if (els.btnSelectStaff) els.btnSelectStaff.classList.remove("is-active");
      if (els.loginStudentBlock) els.loginStudentBlock.style.display = "block";
      if (els.loginStaffBlock) els.loginStaffBlock.style.display = "none";
    });
  }

  if (els.btnSelectStaff) {
    els.btnSelectStaff.addEventListener("click", () => {
      els.btnSelectStaff.classList.add("is-active");
      if (els.btnSelectStudent)
        els.btnSelectStudent.classList.remove("is-active");
      if (els.loginStudentBlock) els.loginStudentBlock.style.display = "none";
      if (els.loginStaffBlock) els.loginStaffBlock.style.display = "block";
    });
  }

  // Login
  els.studentLoginForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleLogin(
      els.studentUsernameInput.value.trim(),
      els.studentPasswordInput.value,
    );
  });

  els.staffLoginForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleLogin(
      els.adminUsernameInput.value.trim(),
      els.adminPasswordInput.value,
    );
  });

  els.logoutBtn.addEventListener("click", handleLogout);

  // Date validation
  els.formStartDate.addEventListener("input", validateFormDates);
  els.formStartDate.addEventListener("change", validateFormDates);
  els.formEndDate.addEventListener("input", validateFormDates);
  els.formEndDate.addEventListener("change", validateFormDates);

  // Form submit & cancel
  els.createRequestForm.addEventListener("submit", handleCreateRequestSubmit);
  els.formCancelBtn.addEventListener("click", handleCancelDraft);

  // Sub-tabs
  if (els.btnSubChat) {
    els.btnSubChat.addEventListener("click", () => switchStudentTab("chat"));
  }
  if (els.btnSubMyRequests) {
    els.btnSubMyRequests.addEventListener("click", () =>
      switchStudentTab("requests"),
    );
  }
  if (els.btnSubForm) {
    els.btnSubForm.addEventListener("click", () => switchStudentTab("form"));
  }

  // Chat
  els.chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const msg = els.chatInput.value.trim();
    if (msg) sendChatMessage(msg);
  });

  document.querySelectorAll(".chip[data-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchStudentTab("chat");
      els.chatInput.value = btn.dataset.msg;
      els.chatInput.focus();
    });
  });

  // Admin filters
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".filter-btn")
        .forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.activeFilter = btn.dataset.filter || "";
      fetchAdminData();
    });
  });

  // Modal Closers
  if (els.closeDetailModalBtn) {
    els.closeDetailModalBtn.addEventListener("click", closeDetailModal);
  }
  if (els.btnCloseDetailModal) {
    els.btnCloseDetailModal.addEventListener("click", closeDetailModal);
  }
  if (els.detailModal) {
    els.detailModal.addEventListener("click", (e) => {
      if (e.target === els.detailModal) closeDetailModal();
    });
  }

  if (els.closeRejectModalBtn) {
    els.closeRejectModalBtn.addEventListener("click", closeRejectModal);
  }
  if (els.cancelRejectBtn) {
    els.cancelRejectBtn.addEventListener("click", closeRejectModal);
  }
  if (els.confirmRejectBtn) {
    els.confirmRejectBtn.addEventListener("click", handleConfirmReject);
  }

  if (els.closeEditModalBtn) {
    els.closeEditModalBtn.addEventListener("click", closeEditModal);
  }
  if (els.cancelEditBtn) {
    els.cancelEditBtn.addEventListener("click", closeEditModal);
  }
  if (els.confirmEditBtn) {
    els.confirmEditBtn.addEventListener("click", handleConfirmEdit);
  }
}

// Global exports
window.openDetailModal = openDetailModal;
window.handleCancelStudentRequest = handleCancelStudentRequest;
window.handleApproveRequest = handleApproveRequest;
window.openRejectModal = openRejectModal;
window.openEditModal = openEditModal;
window.closeDetailModal = closeDetailModal;
window.closeRejectModal = closeRejectModal;
window.closeEditModal = closeEditModal;

function boot() {
  bindEvents();
  if (els.chatLog) els.chatLog.innerHTML = "";
  checkAuthSession();
}

boot();
