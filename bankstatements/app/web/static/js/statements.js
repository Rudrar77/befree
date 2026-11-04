/**
 * Statements list page controller.
 */

import { apiRequest, showToast } from './api.js';
import { formatDate } from './dates.js';

let currentPage = 1;
let currentFilter = '';

export async function loadStatements(page = 1, status = '') {
  currentPage = page;
  currentFilter = status;
  const tbody = document.getElementById('statementsTableBody');
  if (!tbody) return;

  tbody.replaceChildren();
  const trLoading = document.createElement('tr');
  const tdLoading = document.createElement('td');
  tdLoading.colSpan = 8;
  tdLoading.className = 'text-center py-4 text-muted';
  tdLoading.textContent = 'Loading statements...';
  trLoading.appendChild(tdLoading);
  tbody.appendChild(trLoading);

  try {
    let url = `/api/statements?page=${page}&page_size=15`;
    if (status) {
      url += `&processing_status=${encodeURIComponent(status)}`;
    }
    const data = await apiRequest(url);

    tbody.replaceChildren();

    if (!data.items || data.items.length === 0) {
      const trEmpty = document.createElement('tr');
      const tdEmpty = document.createElement('td');
      tdEmpty.colSpan = 8;
      tdEmpty.className = 'text-center py-4 text-muted';
      tdEmpty.textContent = 'No statements found.';
      trEmpty.appendChild(tdEmpty);
      tbody.appendChild(trEmpty);
      renderPagination(0, 1, 15);
      return;
    }

    data.items.forEach(stmt => {
      const tr = document.createElement('tr');

      // Filename
      const tdName = document.createElement('td');
      const link = document.createElement('a');
      link.href = `/statements/${stmt.id}`;
      link.className = 'fw-bold text-decoration-none';
      link.textContent = stmt.original_filename;
      tdName.appendChild(link);

      // Bank
      const tdBank = document.createElement('td');
      tdBank.textContent = stmt.bank_name || '—';

      // Period
      const tdPeriod = document.createElement('td');
      if (stmt.period_start && stmt.period_end) {
        tdPeriod.textContent = `${formatDate(stmt.period_start)} to ${formatDate(stmt.period_end)}`;
      } else {
        tdPeriod.textContent = '—';
      }

      // Status
      const tdStatus = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = `badge bg-${getStatusColor(stmt.processing_status)}`;
      badge.textContent = (stmt.processing_status || '').replace('_', ' ');
      tdStatus.appendChild(badge);

      // Transaction count
      const tdTxnCount = document.createElement('td');
      tdTxnCount.textContent = stmt.transaction_count;

      // Needs review flag
      const tdReview = document.createElement('td');
      if (stmt.needs_review) {
        const flag = document.createElement('span');
        flag.className = 'badge bg-warning text-dark';
        flag.textContent = 'Needs Review';
        tdReview.appendChild(flag);
      } else {
        tdReview.textContent = '—';
      }

      // Created date
      const tdDate = document.createElement('td');
      tdDate.textContent = formatDate(stmt.created_at);

      // Actions
      const tdActions = document.createElement('td');
      tdActions.className = 'text-end';

      const openBtn = document.createElement('a');
      openBtn.href = `/statements/${stmt.id}`;
      openBtn.className = 'btn btn-sm btn-outline-primary me-1';
      openBtn.textContent = 'Open';

      const processBtn = document.createElement('button');
      processBtn.className = 'btn btn-sm btn-outline-secondary me-1';
      processBtn.textContent = 'Process';
      processBtn.disabled = stmt.processing_status === 'processing';
      processBtn.addEventListener('click', async () => {
        try {
          await apiRequest(`/api/statements/${stmt.id}/process`, { method: 'POST' });
          showToast(`Started processing ${stmt.original_filename}`, 'info');
          loadStatements(currentPage, currentFilter);
        } catch (e) {}
      });

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-sm btn-outline-danger';
      deleteBtn.textContent = 'Delete';
      deleteBtn.addEventListener('click', async () => {
        if (confirm(`Are you sure you want to delete ${stmt.original_filename}?`)) {
          try {
            await apiRequest(`/api/statements/${stmt.id}`, { method: 'DELETE' });
            showToast(`Deleted ${stmt.original_filename}`, 'success');
            loadStatements(currentPage, currentFilter);
          } catch (e) {}
        }
      });

      tdActions.appendChild(openBtn);
      tdActions.appendChild(processBtn);
      tdActions.appendChild(deleteBtn);

      tr.appendChild(tdName);
      tr.appendChild(tdBank);
      tr.appendChild(tdPeriod);
      tr.appendChild(tdStatus);
      tr.appendChild(tdTxnCount);
      tr.appendChild(tdReview);
      tr.appendChild(tdDate);
      tr.appendChild(tdActions);

      tbody.appendChild(tr);
    });

    renderPagination(data.total, data.page, data.page_size);
  } catch (err) {
    tbody.replaceChildren();
    const trErr = document.createElement('tr');
    const tdErr = document.createElement('td');
    tdErr.colSpan = 8;
    tdErr.className = 'text-center py-4 text-danger';
    tdErr.textContent = 'Failed to load statements. Please try again.';
    trErr.appendChild(tdErr);
    tbody.appendChild(trErr);
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

function renderPagination(total, page, pageSize) {
  const container = document.getElementById('statementsPagination');
  if (!container) return;
  container.replaceChildren();

  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return;

  const ul = document.createElement('ul');
  ul.className = 'pagination pagination-sm mb-0';

  for (let i = 1; i <= totalPages; i++) {
    const li = document.createElement('li');
    li.className = `page-item ${i === page ? 'active' : ''}`;
    const btn = document.createElement('button');
    btn.className = 'page-link';
    btn.textContent = i;
    btn.addEventListener('click', () => loadStatements(i, currentFilter));
    li.appendChild(btn);
    ul.appendChild(li);
  }

  container.appendChild(ul);
}

