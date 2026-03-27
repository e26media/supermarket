/**
 * app.js — Salethur Supermarket HTMX frontend
 * Handles: barcode scanner, view transitions, cart utils, theme
 */

/* ── Theme (persisted to localStorage) ─────────────── */
(function () {
  const saved = localStorage.getItem('theme') || 'dark';
  if (saved === 'light') document.documentElement.classList.add('light');
})();

function toggleTheme() {
  const html = document.documentElement;
  html.classList.toggle('light');
  localStorage.setItem('theme', html.classList.contains('light') ? 'light' : 'dark');
  const tog = document.getElementById('theme-toggle');
  if (tog) tog.classList.toggle('on');
}

/* ── HTMX config ────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  // Set auth header on every HTMX request
  document.body.addEventListener('htmx:configRequest', function (e) {
    const token = localStorage.getItem('auth_token');
    if (token) {
      e.detail.headers['Authorization'] = 'Bearer ' + token;
    }
  });

  // Show toast on HTMX errors  
  document.body.addEventListener('htmx:responseError', function (e) {
    showToast('Request failed: ' + e.detail.xhr.status, 'error');
  });

  // Handle sidebar active state after HTMX navigation
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target.classList.contains('main-area')) {
      const path = window.location.pathname;
      const segments = path.split('/').filter(Boolean);
      const page = segments[segments.length - 1] || 'pos';
      setActiveNav(page);
    }
  });
});

/* ── Auth helpers ───────────────────────────────────── */
function saveAuth(token, role, username, userId) {
  localStorage.setItem('auth_token', token);
  localStorage.setItem('auth_role', role);
  localStorage.setItem('auth_username', username);
  localStorage.setItem('auth_user_id', userId);
}

function clearAuth() {
  ['auth_token', 'auth_role', 'auth_username', 'auth_user_id'].forEach(k => localStorage.removeItem(k));
}

function getAuthToken() { return localStorage.getItem('auth_token'); }
function getRole() { return localStorage.getItem('auth_role'); }
function getUsername() { return localStorage.getItem('auth_username'); }

/* ── Login form submission ──────────────────────────── */
async function handleLogin(e) {
  e.preventDefault();
  const form = e.target;
  const btn = form.querySelector('.btn-primary');
  const errDiv = document.getElementById('login-error');

  btn.disabled = true;
  btn.textContent = 'Signing in…';

  const formData = new FormData(form);
  try {
    const API = window.API_BASE || 'http://127.0.0.1:8000';
    const resp = await fetch(API + '/auth/login', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();
    if (resp.ok) {
      saveAuth(data.access_token, data.role, data.username, data.user_id);
      // Redirect to POS or dashboard
      const target = data.role === 'admin' ? '/app/analytics' : '/app/pos';
      window.location.href = target;
    } else {
      errDiv.textContent = data.detail || 'Invalid credentials';
      errDiv.classList.add('show');
      btn.disabled = false;
      btn.textContent = '🔐 Sign In';
    }
  } catch (err) {
    errDiv.textContent = '⚠️ Cannot connect to backend.';
    errDiv.classList.add('show');
    btn.disabled = false;
    btn.textContent = '🔐 Sign In';
  }
}

/* ── Logout ─────────────────────────────────────────── */
function logout() {
  clearAuth();
  window.location.href = '/';
}

/* ── Sidebar active highlighting ────────────────────── */
function setActiveNav(page) {
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.remove('active');
    if (el.dataset.page === page) el.classList.add('active');
  });
  // Store for page refresh
  localStorage.setItem('current_page', page);
}

// Mark the right nav item on load based on current URL
document.addEventListener('DOMContentLoaded', function () {
  const path = window.location.pathname;
  const segments = path.split('/').filter(Boolean);
  const page = segments[segments.length - 1] || 'pos';
  setActiveNav(page);

  // Check auth on app pages
  if (path.startsWith('/app') && !getAuthToken()) {
    window.location.href = '/';
  }

  // Show role-gated items
  const role = getRole();
  document.querySelectorAll('[data-role-required]').forEach(el => {
    if (el.dataset.roleRequired !== role) el.style.display = 'none';
  });

  // Populate username in sidebar
  const userNameEl = document.getElementById('sidebar-username');
  if (userNameEl) userNameEl.textContent = getUsername() || 'User';
  const userRoleEl = document.getElementById('sidebar-role');
  if (userRoleEl) userRoleEl.textContent = getRole() || 'staff';
});

/* ── Barcode Scanner ────────────────────────────────── */
let barcodeBuffer = '';
let barcodeTimer = null;

document.addEventListener('keypress', function (e) {
  // Only capture when not in a text input (except barcode field)
  const tag = e.target.tagName;
  const isInput = (tag === 'INPUT' || tag === 'TEXTAREA') && e.target.id !== 'barcode-field';
  if (isInput) return;

  clearTimeout(barcodeTimer);
  if (e.key === 'Enter') {
    if (barcodeBuffer.length > 3) {
      processBarcode(barcodeBuffer);
    }
    barcodeBuffer = '';
    return;
  }
  barcodeBuffer += e.key;
  barcodeTimer = setTimeout(() => { barcodeBuffer = ''; }, 150);
});

function processBarcode(code) {
  const input = document.getElementById('barcode-field');
  if (input) input.value = code;

  const token = getAuthToken();
  const API = window.API_BASE || 'http://127.0.0.1:8000';

  fetch(API + '/products/barcode/' + encodeURIComponent(code), {
    headers: { 'Authorization': 'Bearer ' + token }
  })
    .then(r => r.json())
    .then(product => {
      if (product && product.id) {
        addToCart(product.id);
      } else {
        showToast('Product not found: ' + code, 'error');
      }
    })
    .catch(() => showToast('Barcode lookup failed', 'error'));
}

/* ── Cart operations ────────────────────────────────── */
// Cart is managed server-side keyed to session; these call HTMX endpoints
function addToCart(productId) {
  htmx.ajax('POST', '/pos/cart/add/' + productId, {
    target: '#cart-section',
    swap: 'innerHTML'
  });
  showToast('Added to cart', 'success');
}

function changeQty(cartItemId, delta) {
  htmx.ajax('PATCH', '/pos/cart/qty/' + cartItemId + '?delta=' + delta, {
    target: '#cart-section',
    swap: 'innerHTML'
  });
}

function removeCartItem(cartItemId) {
  htmx.ajax('DELETE', '/pos/cart/item/' + cartItemId, {
    target: '#cart-section',
    swap: 'innerHTML'
  });
}

function clearCart() {
  htmx.ajax('DELETE', '/pos/cart', {
    target: '#cart-section',
    swap: 'innerHTML'
  });
}

/* ── Payment modal ──────────────────────────────────── */
function openPaymentModal() {
  htmx.ajax('GET', '/pos/modal/customer', {
    target: '#modal-container',
    swap: 'innerHTML'
  });
}

function closeModal() {
  document.getElementById('modal-container').innerHTML = '';
}

/* ── Toast notifications ────────────────────────────── */
function showToast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(60px)';
    toast.style.transition = '0.3s ease';
    setTimeout(() => toast.remove(), 350);
  }, 2800);
}

/* ── Filter tabs ────────────────────────────────────── */
function setFilterTab(el, status) {
  document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
}

/* ── FAQ accordion ──────────────────────────────────── */
function toggleFaq(el) {
  el.closest('.faq-item').classList.toggle('open');
}

/* ── Analytics range selector ───────────────────────── */
function setRange(el, range) {
  document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

/* ── Scale reading ──────────────────────────────────── */
function readScale() {
  const token = getAuthToken();
  const API = window.API_BASE || 'http://127.0.0.1:8000';

  fetch(API + '/hardware/scale', {
    headers: { 'Authorization': 'Bearer ' + token }
  })
    .then(r => r.json())
    .then(data => {
      if (data.weight) {
        showToast('⚖️ Weight: ' + data.weight + ' ' + (data.unit || 'kg'), 'success');
        const el = document.getElementById('scale-weight');
        if (el) el.textContent = data.weight;
      } else {
        showToast(data.error || 'Scale not responding', 'error');
      }
    });
}
