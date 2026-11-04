/**
 * Statement detail page controller with polling, unresolved-row display, and export triggers.
 */

import { apiRequest, showToast } from './api.js';
import { formatINR } from './money.js';
import { formatDate } from './dates.js';
import { refreshTransactions } from './transactions.js';

let statementId = '';
let pollInterval = null;

export function initStatementDetail(id) {
  statementId = id;
  loadStatementData();
  loadUnresolvedRows();
  setupEventListeners();
}

async function loadStatementData() {
  try {
    const stmt = await apiRequest(`/api/statements/${statementId}`);
    updateOverviewTab(stmt);
    updateProcessingError(stmt.error_message);

    // If currently queued or processing, start polling
    if (stmt.processing_status === 'queued' || stmt.processing_status === 'processing') {
      startPolling();
    } else {
      stopPolling();
    }
  } catch (err) {}
}

function startPolling() {
  if (pollInterval) return;
  const progressBox = document.getElementById('processingProgressBox');
  if (progressBox) progressBox.classList.remove('d-none');

  pollInterval = setInterval(async () => {
    try {
      const statusData = await apiRequest(`/api/statements/${statementId}/status`);
      updateProgressBar(statusData);
      updateProcessingError(statusData.error_message);

      if (['completed', 'completed_with_warnings', 'failed'].includes(statusData.processing_status)) {
        stopPolling();
        if (statusData.processing_status === 'failed') {
          showToast(statusData.error_message || 'Statement processing failed.', 'danger');
        } else {
          showToast(`Processing finished with status: ${statusData.processing_status}`, 'info');
        }
        loadStatementData();
        loadUnresolvedRows();
        refreshTransactions();
      }
    } catch (err) {
      stopPolling();
    }
  }, 2000);
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  const progressBox = document.getElementById('processingProgressBox');
  if (progressBox) progressBox.classList.add('d-none');
}

function updateProcessingError(message) {
  const errorBox = document.getElementById('processingErrorBox');
  if (!errorBox) return;
  errorBox.textContent = message || '';
  errorBox.classList.toggle('d-none', !message);
}

function updateProgressBar(data) {
  const bar = document.getElementById('processingProgressBar');
  const stepText = document.getElementById('currentStepText');
  if (bar) {
    bar.style.width = `${data.progress_percent}%`;
    bar.setAttribute('aria-valuenow', data.progress_percent);
    bar.textContent = `${data.progress_percent}%`;
  }
  if (stepText) {
    stepText.textContent = `Current step: ${data.current_step || 'Processing'} (${data.pages_done || 0}/${data.pages_total || 0} pages)`;
  }
}

function updateOverviewTab(stmt) {
  const setField = (id, val, isINR = false) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (isINR) {
      el.textContent = formatINR(val);
    } else {
      el.textContent = val || 'Not found';
    }
  };

  setField('stmtBankName', stmt.bank_name);
  setField('stmtAccountHolder', stmt.account_holder_name);
  setField('stmtAccountNumber', stmt.account_number_masked);
  setField('stmtIfsc', stmt.ifsc);
  setField('stmtBranch', stmt.branch_name);
  setField('stmtPeriodStart', formatDate(stmt.period_start));
  setField('stmtPeriodEnd', formatDate(stmt.period_end));
  setField('stmtOpeningBal', stmt.opening_balance, true);
  setField('stmtClosingBal', stmt.closing_balance, true);
  setField('stmtPdfType', stmt.pdf_type);
  setField('stmtTxnCount', stmt.transaction_count);

  const statusBadge = document.getElementById('stmtStatusBadge');
  if (statusBadge) {
    statusBadge.textContent = (stmt.processing_status || '').replace('_', ' ');
    statusBadge.className = `badge bg-${getStatusColor(stmt.processing_status)}`;
  }

  // Render page methods table
  const tbody = document.getElementById('pageMethodsTableBody');
  if (tbody && stmt.page_methods) {
    tbody.replaceChildren();
    stmt.page_methods.forEach(pm => {
      const tr = document.createElement('tr');
      const tdPage = document.createElement('td');
      tdPage.textContent = `Page ${pm.page}`;
      const tdMethod = document.createElement('td');
      tdMethod.textContent = pm.method;
      const tdProvider = document.createElement('td');
      tdProvider.textContent = pm.provider || 'Native PDF';
      const tdOcr = document.createElement('td');
      tdOcr.textContent = pm.ocr_used ? 'Yes' : 'No';
      const tdErr = document.createElement('td');
      tdErr.textContent = pm.error || 'None';
      const tdWarnings = document.createElement('td');
      tdWarnings.textContent = Array.isArray(pm.warnings) && pm.warnings.length
        ? pm.warnings.join(' ')
        : 'None';

      tr.appendChild(tdPage);
      tr.appendChild(tdMethod);
      tr.appendChild(tdProvider);
      tr.appendChild(tdOcr);
      tr.appendChild(tdErr);
      tr.appendChild(tdWarnings);
      tbody.appendChild(tr);
    });
  }
}

async function loadUnresolvedRows() {
  const tbody = document.getElementById('unresolvedRowsTableBody');
  if (!tbody) return;

  try {
    const data = await apiRequest(`/api/statements/${statementId}/unresolved`);
    tbody.replaceChildren();

    if (!data.items || data.items.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.className = 'text-center text-muted py-3';
      td.textContent = 'No unresolved rows.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    data.items.forEach(row => {
      const tr = document.createElement('tr');
      const tdPage = document.createElement('td');
      tdPage.textContent = `Page ${row.source_page || '—'}`;
      const tdText = document.createElement('td');
      tdText.className = 'small font-monospace';
      tdText.textContent = row.raw_text;
      const tdReason = document.createElement('td');
      tdReason.textContent = row.reason;
      const tdMethod = document.createElement('td');
      tdMethod.textContent = row.extraction_method || '—';

      tr.appendChild(tdPage);
      tr.appendChild(tdText);
      tr.appendChild(tdReason);
      tr.appendChild(tdMethod);
      tbody.appendChild(tr);
    });
  } catch (err) {}
}

function setupEventListeners() {
  const processBtn = document.getElementById('stmtProcessBtn');
  if (processBtn) {
    processBtn.addEventListener('click', async () => {
      try {
        await apiRequest(`/api/statements/${statementId}/process`, { method: 'POST' });
        showToast('Processing started.', 'info');
        loadStatementData();
      } catch (err) {}
    });
  }

  const exportBtn = document.getElementById('downloadExportBtn');
  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      const fmt = document.getElementById('exportFormatSelect')?.value || 'xlsx';
      try {
        const res = await apiRequest(`/api/export/${statementId}?format=${fmt}`);
        if (res && res.blob) {
          const url = window.URL.createObjectURL(res.blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = res.filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);
        }
      } catch (err) {}
    });
  }
}

function getStatusColor(status) {
  switch (status) {
    case 'completed': return 'success';
    case 'completed_with_warnings': return 'warning text-dark';
    case 'failed': return 'danger';
    case 'processing': return 'primary';
    case 'queued': return 'info text-dark';
    default: return 'secondary';
  }
}
