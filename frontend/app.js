/**
 * Frontend Application Controller for PragyanAI EduPortal
 * Manages Authentication, Session State, Tab Switching, Registration & Dual-OTP Verification,
 * Analytics, Detailed Academic & Parent Profile, Course-Specific Attendance Claims,
 * and Administrative Governance.
 */

// -------------------------------------------------------------
// Normalized API Base URL (Avoids duplicate /api prefix)
// -------------------------------------------------------------
const RAW_API_BASE = (typeof CONFIG !== "undefined" && CONFIG.API_BASE_URL)
  ? CONFIG.API_BASE_URL
  : (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? "http://127.0.0.1:8000"
      : "https://pragyanai-super30-python-project-3.onrender.com");

const API_BASE = RAW_API_BASE.replace(/\/api\/?$/, "");

// -------------------------------------------------------------
// Global Application State & Storage Keys
// -------------------------------------------------------------
const SESSION_KEY = "pragyan_auth_session";
let currentPage = 1;
const pageSize = 10;
let deptChartInstance = null;
let verifyChartInstance = null;
let searchDebounceTimeout = null;
let globalSessions = [];

// Active Student Verification Session for Onboarding
let activeStudent = {
  phone: "",
  email: "",
  phoneVerified: false,
  emailVerified: false,
  phoneTimer: null,
  emailTimer: null
};

// -------------------------------------------------------------
// 🔐 Authentication & Session Persistence Controller
// -------------------------------------------------------------
function getSession() {
  const data = localStorage.getItem(SESSION_KEY);
  try {
    return data ? JSON.parse(data) : null;
  } catch (e) {
    return null;
  }
}

function setSession(role, user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ role, user, timestamp: Date.now() }));
  restoreSession();
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
  restoreSession();
}

function restoreSession() {
  const session = getSession();
  const avatarEl = document.getElementById("sidebar-avatar");
  const usernameEl = document.getElementById("sidebar-username");
  const roleEl = document.getElementById("sidebar-role");
  const authBtn = document.getElementById("sidebar-auth-btn");

  if (!session) {
    // Guest State
    if (avatarEl) avatarEl.innerText = "--";
    if (usernameEl) usernameEl.innerText = "Guest";
    if (roleEl) roleEl.innerText = "Not Authenticated";
    if (authBtn) {
      authBtn.innerText = "Sign In";
      authBtn.className = "btn-sm btn-outline";
      authBtn.onclick = () => openAuthModal("stu-login");
    }
    return;
  }

  // Authenticated State
  const { role, user } = session;
  const displayName = user.full_name || user.username || "User";
  const initials = displayName.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase() || "AI";

  if (avatarEl) avatarEl.innerText = initials;
  if (usernameEl) usernameEl.innerText = displayName;
  if (roleEl) roleEl.innerText = role.toUpperCase();

  if (authBtn) {
    authBtn.innerText = "Logout";
    authBtn.className = "btn-sm btn-danger";
    authBtn.onclick = () => clearSession();
  }

  // Sync active student ID input if student is logged in
  if (role === "student" && user.id) {
    const stuIdInput = document.getElementById("stu-id-input");
    if (stuIdInput) stuIdInput.value = user.id;
  }
}

function openAuthModal(tab = "stu-login") {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.classList.remove("hidden");
  switchModalAuthTab(tab);
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal");
  if (modal) modal.classList.add("hidden");
}

function switchModalAuthTab(tab) {
  const stuForm = document.getElementById("auth-student-login-form");
  const adminForm = document.getElementById("auth-admin-login-form");
  const btnStu = document.getElementById("modal-tab-stu-login");
  const btnAdmin = document.getElementById("modal-tab-admin-login");

  const isStu = tab === "stu-login";
  if (stuForm) stuForm.classList.toggle("hidden", !isStu);
  if (adminForm) adminForm.classList.toggle("hidden", isStu);

  if (btnStu) btnStu.classList.toggle("active", isStu);
  if (btnAdmin) btnAdmin.classList.toggle("active", !isStu);
}

async function handleStudentLogin(e) {
  if (e && e.preventDefault) e.preventDefault();
  const ident = document.getElementById("stu-login-ident")?.value.trim();
  const password = document.getElementById("stu-login-pass")?.value.trim();

  if (!ident || !password) {
    showNotification(null, "Please enter both Email/Phone and Password.", "danger");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/auth/student/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier: ident, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Student login failed.");

    setSession("student", data.user);
    closeAuthModal();
    showNotification(null, `Welcome back, ${data.user.full_name}!`, "success");

    // Route straight to student portal
    switchTab("student-tab");
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function handleAdminLogin(e) {
  if (e && e.preventDefault) e.preventDefault();
  const ident = document.getElementById("admin-login-ident")?.value.trim();
  const password = document.getElementById("admin-login-pass")?.value.trim();

  if (!ident || !password) {
    showNotification(null, "Please enter Admin username/email and password.", "danger");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/auth/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier: ident, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Admin authentication failed.");

    setSession("admin", data.user);
    closeAuthModal();
    showNotification(null, `Welcome Administrator ${data.user.username}!`, "success");

    // Route to Admin Governance dashboard
    switchTab("admin-gov-tab");
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

// -------------------------------------------------------------
// Navigation & Tab Switching
// -------------------------------------------------------------
function switchTab(tabId) {
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

  // Tab Context Initializers
  if (tabId === "admin-tab") {
    loadAllAdminData();
  } else if (tabId === "admin-gov-tab") {
    loadAdminOnboarding();
    loadAdminSessions();
    loadAdminAttendanceAnalytics();
  } else if (tabId === "student-tab") {
    loadStudentDashboardData();
  }
}

// -------------------------------------------------------------
// 🎓 STUDENT PORTAL: COURSE, DETAILED PROFILE & ATTENDANCE
// -------------------------------------------------------------
function loadStudentDashboardData() {
  const sidInput = document.getElementById("stu-id-input");
  const sid = sidInput ? parseInt(sidInput.value, 10) : 1;

  loadStudentDetailedProfile(sid);
  loadStudentEnrolledCourse(sid);
  loadStudentAttendanceHistory(sid);
}

async function loadStudentDetailedProfile(studentId) {
  try {
    const res = await fetch(`${API_BASE}/api/student/profile/${studentId}`);
    if (!res.ok) throw new Error(`Student #${studentId} profile not found.`);
    const data = await res.json();

    // Populate Academic & Institutional Profile
    const fullEl = document.getElementById("prof-fullname");
    const usnEl = document.getElementById("prof-usn");
    const colEl = document.getElementById("prof-college");
    const degEl = document.getElementById("prof-degree");
    const branchEl = document.getElementById("prof-branch");
    const gradEl = document.getElementById("prof-gradyear");
    const deptEl = document.getElementById("prof-department");
    const semEl = document.getElementById("prof-semester");
    const emailEl = document.getElementById("prof-email-readonly");
    const bioEl = document.getElementById("prof-bio");
    const badgeEl = document.getElementById("stu-approval-badge");

    if (fullEl) fullEl.value = data.full_name || "";
    if (usnEl) usnEl.value = data.usn || "";
    if (colEl) colEl.value = data.college_name || "";
    if (degEl) degEl.value = data.degree || "B.Tech";
    if (branchEl) branchEl.value = data.branch || "";
    if (gradEl) gradEl.value = data.graduation_year || 2027;
    if (deptEl) deptEl.value = data.department || "";
    if (semEl) semEl.value = data.semester || 1;
    if (emailEl) emailEl.value = data.email || "";
    if (bioEl) bioEl.value = data.bio || "";

    if (badgeEl) {
      badgeEl.innerText = `Status: ${data.approval_status}`;
      badgeEl.className = `tag ${data.approval_status === "APPROVED" ? "ok" : data.approval_status === "REJECTED" ? "no" : ""}`;
    }

    // Populate Parent / Guardian Details
    const pNameEl = document.getElementById("prof-parent-name");
    const pRelEl = document.getElementById("prof-parent-relation");
    const pPhoneEl = document.getElementById("prof-parent-phone");
    const pEmailEl = document.getElementById("prof-parent-email");

    if (pNameEl) pNameEl.value = data.parent_name || "";
    if (pRelEl) pRelEl.value = data.parent_relation || "Father";
    if (pPhoneEl) pPhoneEl.value = data.parent_phone || "";
    if (pEmailEl) pEmailEl.value = data.parent_email || "";

  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function saveStudentDetailedProfile(e) {
  if (e && e.preventDefault) e.preventDefault();
  const sidInput = document.getElementById("stu-id-input");
  const studentId = sidInput ? parseInt(sidInput.value, 10) : 1;

  const payload = {
    full_name: (document.getElementById("prof-fullname")?.value || "").trim(),
    department: (document.getElementById("prof-department")?.value || "").trim(),
    semester: parseInt(document.getElementById("prof-semester")?.value, 10) || 1,
    bio: (document.getElementById("prof-bio")?.value || "").trim(),
    college_name: (document.getElementById("prof-college")?.value || "").trim(),
    usn: (document.getElementById("prof-usn")?.value || "").trim(),
    degree: (document.getElementById("prof-degree")?.value || "B.Tech").trim(),
    branch: (document.getElementById("prof-branch")?.value || "").trim(),
    graduation_year: parseInt(document.getElementById("prof-gradyear")?.value, 10) || 2027,
    parent_name: (document.getElementById("prof-parent-name")?.value || "").trim(),
    parent_relation: (document.getElementById("prof-parent-relation")?.value || "Parent").trim(),
    parent_phone: (document.getElementById("prof-parent-phone")?.value || "").trim(),
    parent_email: (document.getElementById("prof-parent-email")?.value || "").trim() || null,
  };

  try {
    const res = await fetch(`${API_BASE}/api/student/profile/${studentId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to update profile.");

    showNotification(null, "Profile, College, and Parent details updated successfully!", "success");
  } catch (err) {
    showNotification(null, err.message, "danger");
  }
}

async function loadStudentEnrolledCourse(studentId) {
  const sid = studentId || (document.getElementById("stu-id-input")?.value || 1);
  const tbody = document.getElementById("student-course-sessions-body");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/student/enrolled-course/${sid}`);
    if (!res.ok) throw new Error("Could not retrieve course curriculum.");
    const data = await res.json();

    const titleEl = document.getElementById("course-title-display");
    const codeEl = document.getElementById("course-code-badge");
    const descEl = document.getElementById("course-desc-display");

    if (titleEl) titleEl.innerText = data.course.title;
    if (codeEl) codeEl.innerText = data.course.code;
    if (descEl) descEl.innerText = data.course.description || "Comprehensive deep-tech curriculum.";

    if (!data.sessions || !data.sessions.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center">No sessions scheduled for this course yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.sessions.map(s => {
      let badgeClass = "badge-secondary";
      if (s.attendance_status === "PRESENT") badgeClass = "badge-success";
      if (s.attendance_status === "SUBMITTED") badgeClass = "badge-warning";
      if (s.attendance_status === "ABSENT") badgeClass = "badge-danger";

      const isLocked = s.attendance_status === "PRESENT";

      return `
        <tr>
          <td><strong>${s.session_date}</strong><br><small style="color: #94a3b8;">${s.timing}</small></td>
          <td><strong>${escapeHtml(s.topic)}</strong><br><small style="color: #94a3b8;">${escapeHtml(s.description || '')}</small></td>
          <td>
            <span class="tag ${s.mode === 'Online' ? 'ok' : ''}">${s.mode}</span><br>
            <a href="${s.meeting_link}" target="_blank" style="font-size: 11px; color: #38bdf8; text-decoration: underline;">Open Link / Room</a>
          </td>
          <td>
            <span class="badge ${badgeClass}">${s.attendance_status}</span>
            ${s.remarks ? `<div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">${escapeHtml(s.remarks)}</div>` : ''}
          </td>
          <td style="text-align: right;">
            <button class="btn btn-success btn-sm" ${isLocked ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : ''} onclick="submitAttendanceClaim(${sid}, ${s.session_id}, 'PRESENT')">Present</button>
            <button class="btn btn-secondary btn-sm" ${isLocked ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : ''} onclick="submitAttendanceClaim(${sid}, ${s.session_id}, 'ABSENT')">Absent</button>
          </td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="color: #ef4444;">${err.message}</td></tr>`;
  }
}

async function submitAttendanceClaim(studentId, sessionId, claim) {
  try {
    const res = await fetch(`${API_BASE}/api/student/attendance/mark`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_id: studentId, session_id: sessionId, claim })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Attendance claim failed.");

    showNotification(null, data.message, "success");
    loadStudentEnrolledCourse(studentId);
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
      tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color: #94a3b8;">No attendance history recorded yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(r => `
      <tr>
        <td><strong>${escapeHtml(r.topic)}</strong></td>
        <td>${r.session_date}</td>
        <td>${r.timing}</td>
        <td>${r.mode}</td>
        <td>
          <span class="tag ${r.status === 'PRESENT' ? 'ok' : r.status === 'ABSENT' ? 'no' : ''}">${r.status}</span>
        </td>
        <td style="color: #94a3b8;">${escapeHtml(r.remarks || "-")}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Attendance history load error:", err);
  }
}

// -------------------------------------------------------------
// Registration & Dual-OTP Verification Handlers
// -------------------------------------------------------------
async function handleRegistration(e) {
  if (e && e.preventDefault) e.preventDefault();
  const notify = document.getElementById("notifyMessage");
  const submitBtn = document.getElementById("submitRegBtn");

  const nameInput = document.getElementById("stuName");
  const emailInput = document.getElementById("stuEmail");
  const phoneInput = document.getElementById("stuPhone");
  const deptInput = document.getElementById("stuDept");
  const semInput = document.getElementById("stuSem");
  const passInput = document.getElementById("stuPassword");

  const payload = {
    full_name: nameInput ? nameInput.value.trim() : "",
    email: emailInput ? emailInput.value.trim().toLowerCase() : "",
    phone: phoneInput ? phoneInput.value.trim() : "",
    department: deptInput ? deptInput.value.trim() : "",
    semester: semInput ? (parseInt(semInput.value, 10) || 1) : 1,
    password: passInput ? passInput.value.trim() : "student123",
  };

  if (!payload.full_name || !payload.email || !payload.phone || !payload.password) {
    showNotification(notify, "Please fill in Name, Email, Phone, and Password.", "danger");
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "Registering & Dispatching OTPs...";
  }

  try {
    const res = await fetch(`${API_BASE}/api/auth/student/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || "Registration failed");

    // Cache credentials for subsequent verification
    activeStudent.phone = payload.phone;
    activeStudent.email = payload.email;
    activeStudent.phoneVerified = false;
    activeStudent.emailVerified = false;

    showNotification(notify, `${data.message} Verification OTPs sent.`, "success");

    const phoneLabel = document.getElementById("displayPhoneLabel");
    const emailLabel = document.getElementById("displayEmailLabel");
    if (phoneLabel) phoneLabel.innerText = payload.phone;
    if (emailLabel) emailLabel.innerText = payload.email;

    const drawer = document.getElementById("otpDrawer");
    if (drawer) drawer.classList.remove("hidden");

    ["phoneVerifyBadge", "emailVerifyBadge"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerText = "";
    });
    ["phoneOtpInput", "emailOtpInput"].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.value = ""; el.disabled = false; }
    });
    ["btnVerifyPhone", "btnVerifyEmail"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = false;
    });

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
  const inputEl = document.getElementById(isPhone ? "phoneOtpInput" : "emailOtpInput");
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
// Developer / Active OTP Inspector
// -------------------------------------------------------------
async function fetchActiveOtpDebug() {
  const container = document.getElementById("debugCodesContainer");
  if (!container) return;

  container.classList.remove("hidden");
  container.innerHTML = `<span style="color: #94a3b8; font-size: 12px;">Querying active test codes...</span>`;

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
    container.innerHTML = `<span style="color: #ef4444; font-size: 12px;">Failed to load active codes.</span>`;
  }
}

// -------------------------------------------------------------
// 🛡️ ADMIN GOVERNANCE HANDLERS
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
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color: #94a3b8;">No student applications found.</td></tr>`;
      return;
    }

    tbody.innerHTML = students.map(s => `
      <tr>
        <td>#${s.id}</td>
        <td><strong>${escapeHtml(s.full_name)}</strong></td>
        <td>${escapeHtml(s.email)}</td>
        <td>${escapeHtml(s.phone)}</td>
        <td>E: ${s.email_verified ? "✅" : "❌"} | P: ${s.phone_verified ? "✅" : "❌"}</td>
        <td>
          <span class="tag ${s.approval_status === 'APPROVED' ? 'ok' : s.approval_status === 'REJECTED' ? 'no' : ''}">${s.approval_status}</span>
        </td>
        <td style="text-align: right;">
          <button onclick="actionOnboarding(${s.id}, 'APPROVED')" class="btn btn-success btn-sm">Approve</button>
          <button onclick="actionOnboarding(${s.id}, 'REJECTED')" class="btn btn-secondary btn-sm">Reject</button>
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
    course_id: 1,
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
      tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="color: #94a3b8;">No approved students found for this session.</td></tr>`;
      return;
    }

    tbody.innerHTML = roster.map(r => `
      <tr>
        <td>#${r.student_id}</td>
        <td><strong>${escapeHtml(r.full_name)}</strong></td>
        <td>
          <span class="tag ${r.status === 'PRESENT' ? 'ok' : r.status === 'ABSENT' ? 'no' : ''}">${r.status}</span>
        </td>
        <td style="color: #94a3b8;">${escapeHtml(r.remarks || "-")}</td>
        <td style="text-align: right;">
          <button onclick="reviewAttendance(${select.value}, ${r.student_id}, 'PRESENT')" class="btn btn-success btn-sm">Approve Present</button>
          <button onclick="reviewAttendance(${select.value}, ${r.student_id}, 'ABSENT')" class="btn btn-secondary btn-sm">Mark Absent</button>
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
        remarks: `Reviewed and confirmed as ${statusDecision} by instructor`,
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
      tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color: #94a3b8;">No session analytics available.</td></tr>`;
      return;
    }

    tbody.innerHTML = analytics.map(a => `
      <tr>
        <td><strong>${escapeHtml(a.topic)}</strong></td>
        <td>${a.session_date}</td>
        <td>${a.mode}</td>
        <td style="color: #10b981; font-weight: bold;">${a.present_count}</td>
        <td style="color: #ef4444; font-weight: bold;">${a.absent_count}</td>
        <td style="color: #f59e0b; font-weight: bold;">${a.submitted_count}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Admin analytics load error:", err);
  }
}

// -------------------------------------------------------------
// Analytics & Chart.js Visualizations
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
  if (el) {
    el.classList.remove("hidden");
    el.innerText = message;
    el.style.borderColor = type === "success" ? "#10b981" : "#ef4444";
    el.style.background = type === "success" ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)";
    el.style.color = type === "success" ? "#10b981" : "#ef4444";
    return;
  }

  const banner = document.getElementById("status-banner");
  if (!banner) return;

  const isSuccess = type === "success";
  banner.textContent = message;
  banner.className = `notify ${isSuccess ? "ok" : "danger"}`;
  banner.style.display = "block";
  banner.style.background = isSuccess ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)";
  banner.style.color = isSuccess ? "#10b981" : "#ef4444";
  banner.style.borderColor = isSuccess ? "#10b981" : "#ef4444";
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
// Global Window Aliases & Initializer
// -------------------------------------------------------------
window.registerStudent = handleRegistration;
window.verifyOTP = verifyOTP;
window.handleResendOTP = handleResendOTP;
window.publishAcademicSession = publishAcademicSession;
window.submitAttendanceClaim = submitAttendanceClaim;
window.loadStudentDashboardData = loadStudentDashboardData;
window.loadStudentEnrolledCourse = loadStudentEnrolledCourse;
window.saveStudentDetailedProfile = saveStudentDetailedProfile;
window.openAuthModal = openAuthModal;
window.closeAuthModal = closeAuthModal;
window.switchModalAuthTab = switchModalAuthTab;
window.handleStudentLogin = handleStudentLogin;
window.handleAdminLogin = handleAdminLogin;
window.actionOnboarding = actionOnboarding;
window.reviewAttendance = reviewAttendance;
window.loadAdminRoster = loadAdminRoster;
window.loadAdminOnboarding = loadAdminOnboarding;
window.loadAdminAttendanceAnalytics = loadAdminAttendanceAnalytics;
window.fetchActiveOtpDebug = fetchActiveOtpDebug;
window.changePage = changePage;
window.debounceSearch = debounceSearch;
window.resetAndFetchTable = resetAndFetchTable;
window.loadAllAdminData = loadAllAdminData;
window.switchTab = switchTab;

window.addEventListener("DOMContentLoaded", () => {
  restoreSession();
  loadAllAdminData();
});
