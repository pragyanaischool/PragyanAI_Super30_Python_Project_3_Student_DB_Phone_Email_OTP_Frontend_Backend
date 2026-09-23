/**
 * Frontend Application Controller for EduPortal
 * Manages Tab Switching, Analytics Visualization, Directory Filtering,
 * Independent 2-Step OTP Dispatch/Resend, and Verification Inspector.
 */

// Resolved API Base URL from frontend/config.js with fallback
const API_BASE = (typeof CONFIG !== "undefined" && CONFIG.API_BASE_URL)
  ? CONFIG.API_BASE_URL
  : (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? "http://127.0.0.1:8000/api"
      : "https://https-gipragyanai-super30-python-project.onrender.com/api");

// Global Application State
let currentPage = 1;
const pageSize = 10;
let deptChartInstance = null;
let verifyChartInstance = null;
let searchDebounceTimeout = null;

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
  document.querySelectorAll(".tab-pane").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(el => el.classList.remove("active"));

  const targetPane = document.getElementById(tabId);
  const targetBtn = document.getElementById(`btn-${tabId}`);

  if (targetPane) targetPane.classList.add("active");
  if (targetBtn) targetBtn.classList.add("active");

  if (tabId === "admin-tab") {
    loadAllAdminData();
  }
}

// -------------------------------------------------------------
// Analytics & Chart.js Visualizations
// -------------------------------------------------------------
async function loadAnalytics() {
  try {
    const res = await fetch(`${API_BASE}/analytics`);
    if (!res.ok) throw new Error(`Analytics API returned HTTP ${res.status}`);
    const data = await res.json();

    // 1. Update KPI Cards
    const kpiTotal = document.getElementById("kpi-total");
    const kpiVerified = document.getElementById("kpi-verified");
    const kpiPending = document.getElementById("kpi-pending");
    const kpiRate = document.getElementById("kpi-rate");

    if (kpiTotal) kpiTotal.innerText = Number(data.kpis?.total_students || 0).toLocaleString();
    if (kpiVerified) kpiVerified.innerText = Number(data.kpis?.fully_verified || 0).toLocaleString();
    if (kpiPending) kpiPending.innerText = Number(data.kpis?.partially_verified || 0).toLocaleString();
    if (kpiRate) kpiRate.innerText = `${data.kpis?.verification_rate || 0}%`;

    // 2. Bar Chart: Department Distribution
    const deptLabels = Object.keys(data.department_distribution || {});
    const deptValues = Object.values(data.department_distribution || {});

    if (deptChartInstance) {
      deptChartInstance.destroy();
    }

    const deptCanvas = document.getElementById("deptChart");
    if (deptCanvas) {
      const deptCtx = deptCanvas.getContext("2d");
      deptChartInstance = new Chart(deptCtx, {
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
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "#151d30",
              titleColor: "#f8fafc",
              bodyColor: "#94a3b8",
              borderColor: "#222f49",
              borderWidth: 1
            }
          },
          scales: {
            x: {
              ticks: { color: "#94a3b8", font: { size: 11 } },
              grid: { color: "#222f49" }
            },
            y: {
              beginAtZero: true,
              ticks: { color: "#94a3b8", stepSize: 5 },
              grid: { color: "#222f49" }
            }
          }
        }
      });
    }

    // 3. Doughnut Chart: Verification Breakdown
    const verifyLabels = Object.keys(data.verification_breakdown || {});
    const verifyValues = Object.values(data.verification_breakdown || {});

    if (verifyChartInstance) {
      verifyChartInstance.destroy();
    }

    const verifyCanvas = document.getElementById("verifyChart");
    if (verifyCanvas) {
      const verifyCtx = verifyCanvas.getContext("2d");
      verifyChartInstance = new Chart(verifyCtx, {
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
              labels: {
                color: "#94a3b8",
                boxWidth: 12,
                padding: 12,
                font: { size: 11 }
              }
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

  try {
    const res = await fetch(`${API_BASE}/students?${params.toString()}`);
    if (!res.ok) throw new Error(`Student API returned HTTP ${res.status}`);
    const result = await res.json();

    if (!tbody) return;
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
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td>${escapeHtml(s.email)}</td>
        <td>${escapeHtml(s.phone)}</td>
        <td>${escapeHtml(s.department)}</td>
        <td>Sem ${s.semester}</td>
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
    if (tbody) {
      tbody.innerHTML = `
        <tr><td colspan="8" class="text-center" style="color: #ef4444;">Error fetching data. Verify that your backend server is online.</td></tr>
      `;
    }
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
// Student Registration & OTP Flow
// -------------------------------------------------------------
async function handleRegistration(e) {
  e.preventDefault();
  const notify = document.getElementById("notifyMessage");
  const submitBtn = document.getElementById("submitRegBtn");

  const nameVal = document.getElementById("stuName").value.trim();
  const emailVal = document.getElementById("stuEmail").value.trim();
  const phoneVal = document.getElementById("stuPhone").value.trim();
  const deptVal = document.getElementById("stuDept").value;
  const semVal = parseInt(document.getElementById("stuSem").value, 10);

  const payload = {
    name: nameVal,
    email: emailVal,
    phone: phoneVal,
    department: deptVal,
    semester: semVal
  };

  submitBtn.disabled = true;
  submitBtn.innerText = "Registering & Dispatching OTPs...";

  try {
    const res = await fetch(`${API_BASE}/students/register`, {
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

    // Populate target labels
    const phoneLabel = document.getElementById("displayPhoneLabel");
    const emailLabel = document.getElementById("displayEmailLabel");
    if (phoneLabel) phoneLabel.innerText = payload.phone;
    if (emailLabel) emailLabel.innerText = payload.email;

    // Display the verification drawer and reset field states
    const drawer = document.getElementById("otpDrawer");
    if (drawer) drawer.classList.remove("hidden");

    document.getElementById("phoneVerifyBadge").innerText = "";
    document.getElementById("emailVerifyBadge").innerText = "";
    document.getElementById("phoneOtpInput").value = "";
    document.getElementById("emailOtpInput").value = "";
    document.getElementById("phoneOtpInput").disabled = false;
    document.getElementById("emailOtpInput").disabled = false;
    document.getElementById("btnVerifyPhone").disabled = false;
    document.getElementById("btnVerifyEmail").disabled = false;

    // Reset inspector box
    const debugBox = document.getElementById("debugCodesContainer");
    if (debugBox) {
      debugBox.classList.add("hidden");
      debugBox.innerHTML = "";
    }

    // Start 30s cooldown timer on both resend buttons
    startCooldownTimer("phone", 30);
    startCooldownTimer("email", 30);

  } catch (err) {
    showNotification(notify, err.message, "danger");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = "Register & Send OTPs";
  }
}

// -------------------------------------------------------------
// Verification & Individual Resend Logic
// -------------------------------------------------------------
async function verifyOTP(type) {
  const notify = document.getElementById("notifyMessage");
  const isPhone = type === "phone";

  const identifier = isPhone ? activeStudent.phone : activeStudent.email;
  const inputId = isPhone ? "phoneOtpInput" : "emailOtpInput";
  const btnId = isPhone ? "btnVerifyPhone" : "btnVerifyEmail";
  const badgeId = isPhone ? "phoneVerifyBadge" : "emailVerifyBadge";
  const resendBtnId = isPhone ? "btnResendPhone" : "btnResendEmail";

  const inputEl = document.getElementById(inputId);
  const otp = inputEl ? inputEl.value.trim() : "";

  if (!otp || otp.length < 4) {
    showNotification(notify, `Please enter a valid 6-digit ${type} OTP.`, "danger");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/students/verify-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, otp, type })
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || "Verification failed");

    showNotification(notify, `✓ ${data.message}`, "success");

    // Lock input and button
    document.getElementById(inputId).disabled = true;
    document.getElementById(btnId).disabled = true;
    const resendBtn = document.getElementById(resendBtnId);
    if (resendBtn) resendBtn.disabled = true;

    // Update badge indicator
    const badge = document.getElementById(badgeId);
    badge.innerText = "✓ Verified";
    badge.style.color = "#10b981";

    // Track state
    if (isPhone) activeStudent.phoneVerified = true;
    else activeStudent.emailVerified = true;

    // Refresh analytics in background
    loadAnalytics();

    // Check if entire verification completed
    if (activeStudent.phoneVerified && activeStudent.emailVerified) {
      showNotification(notify, "🎉 All credentials verified! Student registered successfully.", "success");
      fetchTableData();
    }

  } catch (err) {
    showNotification(notify, err.message, "danger");
  }
}

async function handleResendOTP(channel) {
  const notify = document.getElementById("notifyMessage");
  const isPhone = channel === "phone";
  const identifier = isPhone ? activeStudent.phone : activeStudent.email;
  const resendBtnId = isPhone ? "btnResendPhone" : "btnResendEmail";

  if (!identifier) {
    showNotification(notify, "No active registration in progress. Please register first.", "danger");
    return;
  }

  const resendBtn = document.getElementById(resendBtnId);
  if (resendBtn) resendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/students/resend-otp/${channel}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier })
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || `Failed to resend ${channel} code.`);

    showNotification(notify, `✓ ${data.message}`, "success");

    // Reset inspection box if user fetches new codes
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
  const btnId = isPhone ? "btnResendPhone" : "btnResendEmail";
  const btn = document.getElementById(btnId);
  if (!btn) return;

  // Clear existing timer if any
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
      fetch(`${API_BASE}/debug/recent-otp?identifier=${phoneQuery}`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API_BASE}/debug/recent-otp?identifier=${emailQuery}`).then(r => r.ok ? r.json() : null).catch(() => null)
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
// Utilities
// -------------------------------------------------------------
function showNotification(el, message, type) {
  if (!el) return;
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
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.innerText = String(text);
  return div.innerHTML;
}

// Initial bootstrap upon DOM ready
window.addEventListener("DOMContentLoaded", () => {
  loadAllAdminData();
});
