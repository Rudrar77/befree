/**
 * API client module wrapping fetch with CSRF protection and Appendix A2 error handling.
 */

export function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

export function showToast(message, type = 'danger') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-bg-${type} border-0 show mb-2`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');
  toastEl.setAttribute('aria-atomic', 'true');

  const dFlex = document.createElement('div');
  dFlex.className = 'd-flex';

  const toastBody = document.createElement('div');
  toastBody.className = 'toast-body';
  toastBody.textContent = message;

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
  closeBtn.setAttribute('data-bs-dismiss', 'toast');
  closeBtn.setAttribute('aria-label', 'Close');
  closeBtn.addEventListener('click', () => toastEl.remove());

  dFlex.appendChild(toastBody);
  dFlex.appendChild(closeBtn);
  toastEl.appendChild(dFlex);
  container.appendChild(toastEl);

  setTimeout(() => {
    if (toastEl.parentNode) {
      toastEl.remove();
    }
  }, 6000);
}

export async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith('/') ? endpoint : `/api/${endpoint}`;
  const headers = options.headers ? { ...options.headers } : {};

  // Add CSRF token for mutating methods
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const token = getCsrfToken();
    if (token) {
      headers['X-CSRFToken'] = token;
    }
  }

  // Set default JSON Content-Type if body is not FormData
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    // 204 No Content
    if (response.status === 204) {
      return null;
    }

    // Check if downloading binary file
    const disposition = response.headers.get('Content-Disposition');
    if (disposition && disposition.includes('attachment')) {
      const blob = await response.blob();
      return { blob, filename: extractFilename(disposition) };
    }

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const errorObj = data && data.error ? data.error : {
        code: 'HTTP_ERROR',
        message: response.statusText || 'Request failed.',
      };
      const error = new Error(errorObj.message);
      error.code = errorObj.code;
      error.details = errorObj.details;
      error.status = response.status;
      showToast(`${errorObj.code}: ${errorObj.message}`, 'danger');
      throw error;
    }

    return data;
  } catch (err) {
    if (err.status) {
      throw err;
    }
    // Network or parse error
    showToast(`Network Error: ${err.message}`, 'danger');
    throw err;
  }
}

function extractFilename(header) {
  const match = header.match(/filename=["']?([^"';]+)["']?/i);
  return match ? match[1] : 'download';
}

