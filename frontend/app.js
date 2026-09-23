/**
 * Frontend Application Controller for PragyanAI EduPortal
 * Manages Tab Switching, Registration & Dual-OTP Verification, Analytics,
 * Student Profile & Attendance Portal, and Administrative Governance.
 */

// -------------------------------------------------------------
// Normalized API Base URL (Avoids duplicate /api prefix)
// -------------------------------------------------------------
const RAW_API_BASE = (typeof CONFIG !== "undefined" && CONFIG.API_BASE_URL)
  ? CONFIG.API_BASE_URL
  : (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? "http://127.0.0.1:8000"
      : "https://https-gipragyanai-super30-python-project.onrender.com");

const API_BASE = RAW_API_BASE.replace(/\/api\/?$/, "");

// -------------------------------------------------------------
// Global Application State
// -------------------------------------------------------------
let currentPage = 1;
const pageSize = 10;
let deptChartInstance = null;
let verifyChartInstance = null;
let searchDebounceTimeout = null;
let globalSessions = [];

// Active Student Verification Session
let activeStudent = {
  phone: "",
  email: "",
  phoneVerified: false,
  emailVerified: false,
  phoneTimer: null,
  emailTimer: null
};

// -------------------------------------------------------------
// Navigation & Tab Switching
// -------------------------------------------------------------
function switchTab(tabId) {
  // Support both legacy class names (.tab-pane / .nav-btn) and clean layout classes (.tab-content / .tab-btn)
  document.querySelectorAll(".tab-pane, .tab-content").forEach(el => {
    el.classList.remove("active");
    el.classList.add("hidden");
  });
  document.querySelectorAll(".nav-btn, .tab-btn").forEach(el => {
    el.classList.remove("active", "bg-blue-600", "text-white");
    el.classList.add("text-slate-400");
  });

  const targetPane = document.getElementById(tabId);
  const targetBtn = document.getElementById(`btn-${tabId}`);

  if (targetPane) {
    targetPane.classList.add("active");
    targetPane.classList.remove("hidden");
  }
  if (targetBtn) {
    targetBtn.classList.add("active", "bg-blue-600", "text-white");
    targetBtn.classList.remove("text-slate-400");
  }

  // Contextual initializers
  if (tabId === "admin-tab" || tabId === "tab-admin") {
    loadAllAdminData();
    loadAdminOnboarding();
    loadAdminSessions();
    loadAdminAttendanceAnalytics();
  } else if (tabId === "student-tab" || tabId === "tab-student") {
    loadStudentProfile();
    loadStudentSessions();
  }
}

// -------------------------------------------------------------
// Registration & Dual-OTP Verification Handlers
// -------------------------------------------------------------
async function handleRegistration(e) {
  if (e && e.preventDefault) e.preventDefault();
  const notify = document.getElementById("notifyMessage");
  const submitBtn = document.getElementById("submitRegBtn");

  const nameInput = document.getElementById("stuName") || document.getElementById("reg-name");
  const emailInput = document.getElementById("stuEmail") || document.getElementById("reg-email");
  const phoneInput = document.getElementById("stuPhone") || document.getElementById("reg-phone");
  const deptInput = document.getElementById("stuDept") || document.getElementById("reg-dept");
  const semInput = document.getElementById("stuSem") || document.getElementById("reg-sem");

  const payload = {
    name: nameInput ? nameInput.value.trim() : "",
    email: emailInput ? emailInput.value.trim().toLowerCase() : "",
    phone: phoneInput ? phoneInput.value.trim() : "",
    department: deptInput ? deptInput.value.trim() : "",
    semester: semInput ? (parseInt(semInput.value, 10) || 1) : 1
  };

  if (!payload.name || !payload.email || !payload.phone) {
    showNotification(notify, "Please fill in Name, Email, and Phone number.", "danger");
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "Registering & Dispatching OTPs...";
  }

  try {
    const res = await fetch(`${API_BASE}/api/students/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || "Registration failed");

    // Cache active student verification credentials
    activeStudent.phone = payload.phone;
    activeStudent.email = payload.email;
    activeStudent.phoneVerified = false;
    activeStudent.emailVerified = false;

    showNotification(notify, `${data.message} OTPs sent to ${payload.phone} and ${payload.email}`, "success");

    // Populate target labels / inputs
    const phoneLabel = document.getElementById("displayPhoneLabel");
    const emailLabel = document.getElementById("displayEmailLabel");
    if (phoneLabel) phoneLabel.innerText = payload.phone;
    if (emailLabel) emailLabel.innerText = payload.email;

    const verifyEmailAddr = document.getElementById("verify-email-addr");
    const verifyPhoneNum = document.getElementById("verify-phone-num");
    if (verifyEmailAddr) verifyEmailAddr.value = payload.email;
    if (verifyPhoneNum) verifyPhoneNum.value = payload.phone;

    // Display verification drawer if present
    const drawer = document.getElementById("otpDrawer");
    if (drawer) drawer.classList.remove("hidden");

    // Reset verification input states
    ["phoneVerifyBadge", "emailVerifyBadge"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerText = "";
    });
    ["phoneOtpInput", "emailOtpInput", "verify-phone-otp", "verify-email-otp"].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.value = ""; el.disabled = false; }
    });
    ["btnVerifyPhone", "btnVerifyEmail"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = false;
    });

    // Reset inspector box
    const debugBox = document.getElementById("debugCodesContainer");
    if (debugBox) {
      debugBox.classList.add("hidden");
      debugBox.innerHTML = "";
    }

    // Cooldown timers
    startCooldownTimer("phone", 30);
    startCooldownTimer("email", 30);

  } catch (err) {
    showNotification(notify, err.message, "danger");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "Register & Send OTPs";
    }
  }
}

async function verifyOTP(type) {
  const notify = document.getElementById("notifyMessage");
  const isPhone = type === "phone";

  let identifier = isPhone ? activeStudent.phone : activeStudent.email;
  if (!identifier) {
    const fallbackInput = document.getElementById(isPhone ? "verify-phone-num" : "verify-email-addr");
    if (fallbackInput && fallbackInput.value.trim()) {
      identifier = fallbackInput.value.trim();
    }
  }

  const inputEl = document.getElementById(isPhone ? "phoneOtpInput" : "emailOtpInput") ||
                  document.getElementById(isPhone ? "verify-phone-otp" : "verify-email-otp");
  const otp = inputEl ? inputEl.value.trim() : "";

  if (!otp || otp.length < 4) {
    showNotification(notify, `Please enter a valid 6-digit ${type} OTP.`, "danger");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/students/verify-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, otp, type })
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || "Verification failed");

    showNotification(notify, `✓ ${data.message}`, "success");

    if (inputEl) inputEl.disabled = true;
    const btn = document.getElementById(isPhone ? "btnVerifyPhone" : "btnVerifyEmail");
    if (btn) btn.disabled = true;

    const resendBtn = document.getElementById(isPhone ? "btnResendPhone" : "btnResendEmail");
    if (resendBtn) resendBtn.disabled = true;

    const badge = document.getElementById(isPhone ? "phoneVerifyBadge" : "emailVerifyBadge");
    if (badge) {
      badge.innerText = "✓ Verified";
      badge.style.color = "#10b981";
    }

    if (isPhone) activeStudent.phoneVerified = true;
    else activeStudent.emailVerified = true;

    loadAnalytics();

    if (activeStudent.phoneVerified && activeStudent.emailVerified) {
      showNotification(notify, "🎉 All credentials verified! Student onboarding pending admin approval.", "success");
      fetchTableData();
    }

  } catch (err) {
    showNotification(notify, err.message, "danger");
  }
}

async function handleResendOTP(channel) {
  const notify = document.getElementById("notifyMessage");
  const isPhone = channel === "phone";
  let identifier = isPhone ? activeStudent.phone : activeStudent.email;

  if (!identifier) {
    const fallbackInput = document.getElementById(isPhone ? "verify-phone-num" : "verify-email-addr");
    if (fallbackInput && fallbackInput.value.trim()) {
      identifier = fallbackInput.value.trim();
    }
  }

  if (!identifier) {
    showNotification(notify, "No active registration. Please enter your email or phone first.", "danger");
    return;
  }

  const resendBtn = document.getElementById(isPhone ? "btnResendPhone" : "btnResendEmail");
  if (resendBtn) resendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/students/resend-otp/${channel}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier })
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || `Failed to resend ${channel} code.`);

    showNotification(notify, `✓ ${data.message}`, "success");

    const debugBox = document.getElementById("debugCodesContainer");
    if (debugBox && !debugBox.classList.contains("hidden")) {
      fetchActiveOtpDebug();
    }

    startCooldownTimer(channel, 45);

  } catch (err) {
    showNotification(notify, err.message, "danger");
    if (resendBtn) resendBtn.disabled = false;
  }
}

function startCooldownTimer(channel, seconds) {
  const isPhone = channel === "phone";
  const btn = document.getElementById(isPhone ? "btnResendPhone" : "btnResendEmail");
  if (!btn) return;

  if (isPhone && activeStudent.phoneTimer) clearInterval(activeStudent.phoneTimer);
  if (!isPhone && activeStudent.emailTimer) clearInterval(activeStudent.emailTimer);

  btn.disabled = true;
  let remaining = seconds;

  const timer = setInterval(() => {
    btn.innerText = `Resend (${remaining}s)`;
    remaining--;

    if (remaining < 0) {
      clearInterval(timer);
      btn.disabled = false;
      btn.innerText = isPhone ? "Resend SMS" : "Resend Email";
    }
  }, 1000);

  if (isPhone) activeStudent.phoneTimer = timer;
  else activeStudent.emailTimer = timer;
}

// -------------------------------------------------------------
// Debug / Active OTP Inspector
// -------------------------------------------------------------
async function fetchActiveOtpDebug() {
  const container = document.getElementById("debugCodesContainer");
  if (!container) return;

  container.classList.remove("hidden");
  container.innerHTML = `<span style="color: #94a3b8; font-size: 12px;">Querying server memory for active codes...</span>`;

  try {
    const phoneQuery = encodeURIComponent(activeStudent.phone || "");
    const emailQuery = encodeURIComponent(activeStudent.email || "");

    const [resPhone, resEmail] = await Promise.all([
      fetch(`${API_BASE}/api/debug/recent-otp?identifier=${phoneQuery}`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API_BASE}/api/debug/recent-otp?identifier=${emailQuery}`).then(r => r.ok ? r.json() : null).catch(() => null)
    ]);

    const phoneCode = resPhone?.active_otp || "Expired / Not Found";
    const emailCode = resEmail?.active_otp || "Expired / Not Found";

    container.innerHTML = `
      <div style="background: #151d30; border: 1px solid #222f49; padding: 10px; border-radius: 6px; font-family: monospace; font-size: 13px; text-align: left; margin-top: 8px;">
        <div style="color: #38bdf8; margin-bottom: 4px;">📱 SMS OTP: <strong style="color: #10b981; letter-spacing: 2px;">${phoneCode}</strong></div>
        <div style="color: #38bdf8;">✉️ Email OTP: <strong style="color: #10b981; letter-spacing: 2px;">${emailCode}</strong></div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<span style="color: #ef4444; font-size: 12px;">Failed to fetch debug codes. Verify backend logs.</span>`;
  }
}

// -------------------------------------------------------------
// 🎓 STUDENT PORTAL HANDLERS
// -------------------------------------------------------------
async function loadStudentProfile() {
  const sidInput = document.getElementById("stu-id-input");
  const sid = sidInput ? sidInput.value : 1;

  try {
    const res = await fetch(`${API_BASE}/api/student/profile/${sid}`);
    if (!res.ok) throw new Error(`Student #${sid} not found.`);
    const data = await res.json();

    const nameEl = document.getElementById("stu-name");
    const deptEl = document.getElementById("stu-dept");
    const emailEl = document.getElementById("stu-email");
    const bioEl = document.getElementById("stu-bio");
    const appStatusEl = document.getElementById("stu-approval");

    if (nameEl) nameEl.value = data.full_name || "";
    if (deptEl) deptEl.value = data.department || "";
    if (emailEl) emailEl.value = data.email || "";
    if (bioEl) bioEl.value = data.bio || "";

    if (appStatusEl) {
      appStatusEl.value = data.approval_status;
      appStatusEl.className = `w-full bg-[#0b0f19]/50 border border-[#222f49] rounded-lg p-2.5 text-sm font-semibold cursor-not-allowed ${
        data.approval_status === "APPROVED" ? "text-emerald-400" : data.approval_status === "REJECTED" ? "text-rose-400" : "text-amber-400"
      }`;
    }

    loadStudentAttendanceHistory(sid);
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function saveStudentProfile() {
  const sid = document.getElementById("stu-id-input")?.value || 1;
  const payload = {
    full_name: (document.getElementById("stu-name")?.value || "").trim(),
    department: (document.getElementById("stu-dept")?.value || "").trim(),
    bio: (document.getElementById("stu-bio")?.value || "").trim(),
  };

  try {
    const res = await fetch(`${API_BASE}/api/student/profile/${sid}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Update failed");
    showNotification(null, "Profile updated successfully!", "success");
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function loadStudentSessions() {
  try {
    const res = await fetch(`${API_BASE}/api/student/sessions`);
    globalSessions = await res.json();

    const select = document.getElementById("session-select");
    if (!select) return;

    select.innerHTML = globalSessions
      .map(s => `<option value="${s.id}">${s.topic} (${s.session_date})</option>`)
      .join("");

    displayStudentSessionDetails();
  } catch (err) {
    console.error("Failed to load student sessions:", err);
  }
}

function displayStudentSessionDetails() {
  const select = document.getElementById("session-select");
  if (!select) return;

  const sid = parseInt(select.value, 10);
  const session = globalSessions.find(s => s.id === sid);
  const card = document.getElementById("session-details-card");

  if (!session) {
    if (card) card.classList.add("hidden");
    return;
  }

  if (card) card.classList.remove("hidden");

  const topicEl = document.getElementById("sess-card-topic");
  const descEl = document.getElementById("sess-card-desc");
  const timeEl = document.getElementById("sess-card-time");
  const linkEl = document.getElementById("sess-card-link");
  const modeEl = document.getElementById("sess-card-mode");

  if (topicEl) topicEl.textContent = session.topic;
  if (descEl) descEl.textContent = session.description || "No prerequisites specified.";
  if (timeEl) timeEl.textContent = `${session.session_date} | ${session.timing}`;

  if (linkEl) {
    linkEl.href = session.meeting_link;
    linkEl.textContent = session.meeting_link;
  }

  if (modeEl) {
    modeEl.textContent = session.mode;
    modeEl.className = `px-2 py-0.5 rounded text-xs font-semibold ${
      session.mode === "Online"
        ? "bg-blue-900 text-blue-300"
        : session.mode === "Hybrid"
        ? "bg-purple-900 text-purple-300"
        : "bg-slate-700 text-slate-300"
    }`;
  }
}

async function submitStudentAttendance() {
  const sidInput = document.getElementById("stu-id-input");
  const sessSelect = document.getElementById("session-select");

  const studentId = sidInput ? parseInt(sidInput.value, 10) : 1;
  const sessionId = sessSelect ? parseInt(sessSelect.value, 10) : null;

  if (!sessionId) {
    showNotification(null, "Please select an active session first.", "danger");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/student/attendance/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_id: studentId, session_id: sessionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Attendance submission failed");

    showNotification(null, data.message, "success");
    loadStudentAttendanceHistory(studentId);
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function loadStudentAttendanceHistory(studentId) {
  const tbody = document.getElementById("student-attendance-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/student/attendance/history/${studentId}`);
    const rows = await res.json();

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-3 text-center text-slate-500">No attendance records found.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(r => `
      <tr class="border-b border-[#222f49] hover:bg-[#1a233a]">
        <td class="p-3 font-medium text-white">${escapeHtml(r.topic)}</td>
        <td class="p-3">${r.session_date}</td>
        <td class="p-3">${r.timing}</td>
        <td class="p-3">${r.mode}</td>
        <td class="p-3">
          <span class="px-2 py-0.5 rounded text-[11px] font-semibold ${
            r.status === "PRESENT"
              ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
              : r.status === "ABSENT"
              ? "bg-rose-950 text-rose-400 border border-rose-800"
              : "bg-amber-950 text-amber-400 border border-amber-800"
          }">${r.status}</span>
        </td>
        <td class="p-3 text-slate-400">${escapeHtml(r.remarks || "-")}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Attendance history load error:", err);
  }
}

// -------------------------------------------------------------
// 🛡️ ADMIN DASHBOARD HANDLERS
// -------------------------------------------------------------
async function loadAdminOnboarding() {
  const filterSelect = document.getElementById("admin-onboarding-filter");
  const filter = filterSelect ? filterSelect.value : "ALL";
  const tbody = document.getElementById("admin-onboarding-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/admin/onboarding?status_filter=${filter}`);
    const students = await res.json();

    if (!students.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="p-3 text-center text-slate-500">No student applications found.</td></tr>`;
      return;
    }

    tbody.innerHTML = students.map(s => `
      <tr class="border-b border-[#222f49] hover:bg-[#1a233a]">
        <td class="p-3 font-mono">#${s.id}</td>
        <td class="p-3 font-medium text-white">${escapeHtml(s.full_name)}</td>
        <td class="p-3">${escapeHtml(s.email)}</td>
        <td class="p-3 font-mono">${escapeHtml(s.phone)}</td>
        <td class="p-3">E: ${s.email_verified ? "✅" : "❌"} | P: ${s.phone_verified ? "✅" : "❌"}</td>
        <td class="p-3">
          <span class="font-semibold ${
            s.approval_status === "APPROVED"
              ? "text-emerald-400"
              : s.approval_status === "REJECTED"
              ? "text-rose-400"
              : "text-amber-400"
          }">${s.approval_status}</span>
        </td>
        <td class="p-3 text-right space-x-2">
          <button onclick="actionOnboarding(${s.id}, 'APPROVED')" class="px-2 py-1 bg-emerald-600/80 hover:bg-emerald-600 text-white rounded text-[11px]">Approve</button>
          <button onclick="actionOnboarding(${s.id}, 'REJECTED')" class="px-2 py-1 bg-rose-600/80 hover:bg-rose-600 text-white rounded text-[11px]">Reject</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Admin onboarding load error:", err);
  }
}

async function actionOnboarding(studentId, decision) {
  try {
    const res = await fetch(`${API_BASE}/api/admin/onboarding/${studentId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: decision }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Action failed");

    showNotification(null, data.message, "success");
    loadAdminOnboarding();
    fetchTableData();
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function publishAcademicSession() {
  const payload = {
    topic: (document.getElementById("new-sess-topic")?.value || "").trim(),
    session_date: document.getElementById("new-sess-date")?.value || "",
    timing: (document.getElementById("new-sess-time")?.value || "").trim(),
    mode: document.getElementById("new-sess-mode")?.value || "Online",
    meeting_link: (document.getElementById("new-sess-link")?.value || "").trim(),
    description: (document.getElementById("new-sess-desc")?.value || "").trim(),
  };

  if (!payload.topic || !payload.session_date || !payload.meeting_link) {
    showNotification(null, "Topic, Date, and Meeting Link are required.", "danger");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/admin/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Session creation failed");

    showNotification(null, "Academic session published successfully!", "success");
    loadAdminSessions();
    loadAdminAttendanceAnalytics();
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function loadAdminSessions() {
  try {
    const res = await fetch(`${API_BASE}/api/student/sessions`);
    const sessions = await res.json();
    const select = document.getElementById("admin-session-select");
    if (!select) return;

    select.innerHTML = sessions
      .map(s => `<option value="${s.id}">${s.topic} (${s.session_date})</option>`)
      .join("");

    loadAdminRoster();
  } catch (err) {
    console.error("Admin sessions dropdown error:", err);
  }
}

async function loadAdminRoster() {
  const select = document.getElementById("admin-session-select");
  if (!select || !select.value) return;

  const tbody = document.getElementById("admin-roster-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/admin/sessions/${select.value}/roster`);
    const roster = await res.json();

    if (!roster.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="p-3 text-center text-slate-500">No approved students found for this session.</td></tr>`;
      return;
    }

    tbody.innerHTML = roster.map(r => `
      <tr class="border-b border-[#222f49] hover:bg-[#1a233a]">
        <td class="p-3 font-mono">#${r.student_id}</td>
        <td class="p-3 font-medium text-white">${escapeHtml(r.full_name)}</td>
        <td class="p-3">
          <span class="px-2 py-0.5 rounded text-[11px] font-semibold ${
            r.status === "PRESENT"
              ? "bg-emerald-950 text-emerald-400"
              : r.status === "ABSENT"
              ? "bg-rose-950 text-rose-400"
              : "bg-amber-950 text-amber-400"
          }">${r.status}</span>
        </td>
        <td class="p-3 text-slate-400">${escapeHtml(r.remarks || "-")}</td>
        <td class="p-3 text-right space-x-2">
          <button onclick="reviewAttendance(${select.value}, ${r.student_id}, 'PRESENT')" class="px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[11px]">Mark Present</button>
          <button onclick="reviewAttendance(${select.value}, ${r.student_id}, 'ABSENT')" class="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded text-[11px]">Mark Absent</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Admin roster fetch error:", err);
  }
}

async function reviewAttendance(sessionId, studentId, statusDecision) {
  try {
    const res = await fetch(`${API_BASE}/api/admin/sessions/${sessionId}/attendance/${studentId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: statusDecision,
        remarks: `Marked by Instructor as ${statusDecision}`,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Review failed");

    loadAdminRoster();
    loadAdminAttendanceAnalytics();
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function loadAdminAttendanceAnalytics() {
  const tbody = document.getElementById("admin-analytics-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/admin/analytics/attendance`);
    const analytics = await res.json();

    if (!analytics.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-3 text-center text-slate-500">No session analytics available.</td></tr>`;
      return;
    }

    tbody.innerHTML = analytics.map(a => `
      <tr class="border-b border-[#222f49] hover:bg-[#1a233a]">
        <td class="p-3 font-medium text-white">${escapeHtml(a.topic)}</td>
        <td class="p-3">${a.session_date}</td>
        <td class="p-3">${a.mode}</td>
        <td class="p-3 font-bold text-emerald-400">${a.present_count}</td>
        <td class="p-3 font-bold text-rose-400">${a.absent_count}</td>
        <td class="p-3 font-bold text-amber-400">${a.submitted_count}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Admin analytics load error:", err);
  }
}

// -------------------------------------------------------------
// Analytics & Chart.js Visualizations (Legacy Support)
// -------------------------------------------------------------
async function loadAnalytics() {
  try {
    const res = await fetch(`${API_BASE}/api/analytics`);
    if (!res.ok) throw new Error(`Analytics API returned HTTP ${res.status}`);
    const data = await res.json();

    const kpiTotal = document.getElementById("kpi-total");
    const kpiVerified = document.getElementById("kpi-verified");
    const kpiPending = document.getElementById("kpi-pending");
    const kpiRate = document.getElementById("kpi-rate");

    if (kpiTotal) kpiTotal.innerText = Number(data.kpis?.total_students || 0).toLocaleString();
    if (kpiVerified) kpiVerified.innerText = Number(data.kpis?.fully_verified || 0).toLocaleString();
    if (kpiPending) kpiPending.innerText = Number(data.kpis?.partially_verified || 0).toLocaleString();
    if (kpiRate) kpiRate.innerText = `${data.kpis?.verification_rate || 0}%`;

    const deptLabels = Object.keys(data.department_distribution || {});
    const deptValues = Object.values(data.department_distribution || {});

    if (deptChartInstance) deptChartInstance.destroy();

    const deptCanvas = document.getElementById("deptChart");
    if (deptCanvas && typeof Chart !== "undefined") {
      deptChartInstance = new Chart(deptCanvas.getContext("2d"), {
        type: "bar",
        data: {
          labels: deptLabels,
          datasets: [{
            label: "Enrolled Students",
            data: deptValues,
            backgroundColor: "#3b82f6",
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#94a3b8" }, grid: { color: "#222f49" } },
            y: { beginAtZero: true, ticks: { color: "#94a3b8" }, grid: { color: "#222f49" } }
          }
        }
      });
    }

    const verifyLabels = Object.keys(data.verification_breakdown || {});
    const verifyValues = Object.values(data.verification_breakdown || {});

    if (verifyChartInstance) verifyChartInstance.destroy();

    const verifyCanvas = document.getElementById("verifyChart");
    if (verifyCanvas && typeof Chart !== "undefined") {
      verifyChartInstance = new Chart(verifyCanvas.getContext("2d"), {
        type: "doughnut",
        data: {
          labels: verifyLabels,
          datasets: [{
            data: verifyValues,
            backgroundColor: ["#10b981", "#3b82f6", "#f59e0b", "#ef4444"],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: { color: "#94a3b8", boxWidth: 12, padding: 12 }
            }
          }
        }
      });
    }

  } catch (err) {
    console.error("Failed to load analytics:", err);
  }
}

// -------------------------------------------------------------
// Paginated Student Directory Operations
// -------------------------------------------------------------
async function fetchTableData() {
  const searchInput = document.getElementById("searchBox");
  const deptInput = document.getElementById("deptFilter");
  const statusInput = document.getElementById("statusFilter");

  const search = searchInput ? searchInput.value.trim() : "";
  const department = deptInput ? deptInput.value : "";
  const statusFilter = statusInput ? statusInput.value : "";

  const params = new URLSearchParams({
    page: currentPage,
    limit: pageSize,
    search: search,
    department: department,
    status_filter: statusFilter
  });

  const tbody = document.getElementById("studentTableBody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/students?${params.toString()}`);
    if (!res.ok) throw new Error(`Student API returned HTTP ${res.status}`);
    const result = await res.json();

    tbody.innerHTML = "";

    if (!result.students || result.students.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="color: #94a3b8;">No matching student records found.</td></tr>`;
      const pageInfo = document.getElementById("pageInfo");
      if (pageInfo) pageInfo.innerText = "Showing Page 0 of 0 (0 records)";
      const prevBtn = document.getElementById("prevBtn");
      const nextBtn = document.getElementById("nextBtn");
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
      return;
    }

    result.students.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>#${s.id}</td>
        <td><strong>${escapeHtml(s.full_name || s.name)}</strong></td>
        <td>${escapeHtml(s.email)}</td>
        <td>${escapeHtml(s.phone)}</td>
        <td>${escapeHtml(s.department)}</td>
        <td>Sem ${s.semester || "-"}</td>
        <td><span class="tag ${s.phone_verified ? 'ok' : 'no'}">${s.phone_verified ? '✓ Verified' : 'Pending'}</span></td>
        <td><span class="tag ${s.email_verified ? 'ok' : 'no'}">${s.email_verified ? '✓ Verified' : 'Pending'}</span></td>
      `;
      tbody.appendChild(tr);
    });

    const totalPages = result.total_pages || 1;
    const pageInfo = document.getElementById("pageInfo");
    if (pageInfo) {
      pageInfo.innerText = `Showing Page ${result.page} of ${totalPages} (${result.total} records)`;
    }
    const prevBtn = document.getElementById("prevBtn");
    const nextBtn = document.getElementById("nextBtn");
    if (prevBtn) prevBtn.disabled = result.page <= 1;
    if (nextBtn) nextBtn.disabled = result.page >= totalPages;

  } catch (err) {
    console.error("Directory fetch error:", err);
    tbody.innerHTML = `
      <tr><td colspan="8" class="text-center" style="color: #ef4444;">Error fetching data. Backend unreachable.</td></tr>
    `;
  }
}

function debounceSearch() {
  clearTimeout(searchDebounceTimeout);
  searchDebounceTimeout = setTimeout(() => {
    currentPage = 1;
    fetchTableData();
  }, 350);
}

function resetAndFetchTable() {
  currentPage = 1;
  fetchTableData();
}

function changePage(delta) {
  currentPage += delta;
  fetchTableData();
}

function loadAllAdminData() {
  loadAnalytics();
  fetchTableData();
}

// -------------------------------------------------------------
// Utilities & Global Notification Bridge
// -------------------------------------------------------------
function showNotification(el, message, type) {
  // Legacy targeted element support
  if (el) {
    el.classList.remove("hidden");
    el.innerText = message;
    if (type === "success") {
      el.style.borderColor = "#10b981";
      el.style.background = "rgba(16, 185, 129, 0.15)";
      el.style.color = "#10b981";
    } else {
      el.style.borderColor = "#ef4444";
      el.style.background = "rgba(239, 68, 68, 0.15)";
      el.style.color = "#ef4444";
    }
    return;
  }

  // Modern banner fallback
  const banner = document.getElementById("status-banner");
  if (!banner) return;

  const isSuccess = type === "success";
  banner.textContent = message;
  banner.className = `mb-6 p-4 rounded-lg text-sm border font-medium ${
    isSuccess
      ? "bg-emerald-950/60 border-emerald-700 text-emerald-300"
      : "bg-rose-950/60 border-rose-700 text-rose-300"
  }`;
  banner.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
  setTimeout(() => banner.classList.add("hidden"), 6000);
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.innerText = String(text);
  return div.innerHTML;
}

// -------------------------------------------------------------
// Global Aliases for Index Buttons & Initial Setup
// -------------------------------------------------------------
window.registerStudent = handleRegistration;
window.verifyOtp = verifyOTP;
window.resendOtp = handleResendOTP;
window.publishSession = publishAcademicSession;
window.submitAttendance = submitStudentAttendance;

window.addEventListener("DOMContentLoaded", () => {
  loadAllAdminData();
});
