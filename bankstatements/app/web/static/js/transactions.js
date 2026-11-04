/**
 * Transactions table controller with search, filters, drawer, and inline category editing.
 */

import { apiRequest, showToast } from './api.js';
import { formatDate } from './dates.js';
import { formatINR } from './money.js';

let statementIdFilter = null;
let categoriesList = [];
let debounceTimer = null;

export async function initTransactionsView(statementId = null) {
  statementIdFilter = statementId;
  await loadCategories();
  setupFilterControls();
  loadTransactionsFromUrl();
}

async function loadCategories() {
  try {
    const res = await apiRequest('/api/categories');
    categoriesList = res.items || [];
    populateCategoryDropdowns();
  } catch (err) {}
}

function populateCategoryDropdowns() {
  const filterSelect = document.getElementById('filterCategory');
  if (filterSelect) {
    categoriesList.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      filterSelect.appendChild(opt);
    });
  }
}

function setupFilterControls() {
  const searchInput = document.getElementById('searchQuery');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        applyFilters(1);
      }, 300);
    });
  }

  ['filterCategory', 'filterMethod', 'filterValidation', 'filterReview', 'sortSelect'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => applyFilters(1));
    }
  });

  const reclassifyBtn = document.getElementById('reclassifyBtn');
  if (reclassifyBtn && statementIdFilter) {
    reclassifyBtn.addEventListener('click', async () => {
      try {
        const res = await apiRequest('/api/classification/classify', {
          method: 'POST',
          body: JSON.stringify({ statement_id: statementIdFilter, force: false }),
        });
        showToast(`Re-classified: ${res.classified} categorized, ${res.needs_review} need review. Manual edits preserved.`, 'info');
        applyFilters(1);
      } catch (err) {}
    });
  }
}

function getFilterParams(page = 1) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', 50);

  if (statementIdFilter) {
    params.set('statement_id', statementIdFilter);
  }

  const search = document.getElementById('searchQuery')?.value?.trim();
  if (search) params.set('search', search);

  const cat = document.getElementById('filterCategory')?.value;
  if (cat) params.set('category_id', cat);

  const method = document.getElementById('filterMethod')?.value;
  if (method) params.set('classification_method', method);

  const valStatus = document.getElementById('filterValidation')?.value;
  if (valStatus) params.set('validation_status', valStatus);

  const review = document.getElementById('filterReview')?.value;
  if (review === 'true') params.set('needs_review', 'true');

  const sortVal = document.getElementById('sortSelect')?.value || 'transaction_date_desc';
  const [sortBy, sortDir] = sortVal.split('_');
  params.set('sort_by', sortBy === 'date' ? 'transaction_date' : sortBy);
  params.set('sort_dir', sortDir || 'desc');

  return params;
}

export async function applyFilters(page = 1) {
  const params = getFilterParams(page);
  // Persist in URL query string without reloading
  window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
  await fetchAndRenderTransactions(params);
}

export async function refreshTransactions() {
  const urlParams = new URLSearchParams(window.location.search);
  const page = parseInt(urlParams.get('page') || '1', 10);
  await fetchAndRenderTransactions(getFilterParams(page));
}

function loadTransactionsFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  const page = parseInt(urlParams.get('page') || '1', 10);

  if (urlParams.get('search')) {
    const el = document.getElementById('searchQuery');
    if (el) el.value = urlParams.get('search');
  }
  if (urlParams.get('category_id')) {
    const el = document.getElementById('filterCategory');
    if (el) el.value = urlParams.get('category_id');
  }
  if (urlParams.get('classification_method')) {
    const el = document.getElementById('filterMethod');
    if (el) el.value = urlParams.get('classification_method');
  }
  if (urlParams.get('validation_status')) {
    const el = document.getElementById('filterValidation');
    if (el) el.value = urlParams.get('validation_status');
  }
  if (urlParams.get('needs_review') === 'true') {
    const el = document.getElementById('filterReview');
    if (el) el.value = 'true';
  }
  const sortBy = urlParams.get('sort_by');
  const sortDir = urlParams.get('sort_dir');
  if (sortBy || sortDir) {
    const el = document.getElementById('sortSelect');
    if (el) {
      const sortValue = `${sortBy === 'transaction_date' ? 'date' : sortBy || 'date'}_${sortDir || 'desc'}`;
      if (Array.from(el.options).some(option => option.value === sortValue)) {
        el.value = sortValue;
      }
    }
  }

  applyFilters(page);
}

async function fetchAndRenderTransactions(params) {
  const tbody = document.getElementById('transactionsTableBody');
  if (!tbody) return;

  tbody.replaceChildren();
  const trLoading = document.createElement('tr');
  const tdLoading = document.createElement('td');
  tdLoading.colSpan = 7;
  tdLoading.className = 'text-center py-4 text-muted';
  tdLoading.textContent = 'Loading transactions...';
  trLoading.appendChild(tdLoading);
  tbody.appendChild(trLoading);

  try {
    const endpoint = statementIdFilter
      ? `/api/statements/${statementIdFilter}/transactions?${params.toString()}`
      : `/api/transactions?${params.toString()}`;

    const data = await apiRequest(endpoint);
    tbody.replaceChildren();

    if (!data.items || data.items.length === 0) {
      const trEmpty = document.createElement('tr');
      const tdEmpty = document.createElement('td');
      tdEmpty.colSpan = 7;
      tdEmpty.className = 'text-center py-4 text-muted';
      tdEmpty.textContent = 'No matching transactions found.';
      trEmpty.appendChild(tdEmpty);
      tbody.appendChild(trEmpty);
      renderTxnPagination(0, 1, 50);
      return;
    }

    data.items.forEach(t => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';

      // Date
      const tdDate = document.createElement('td');
      tdDate.textContent = formatDate(t.transaction_date);

      // Description
      const tdDesc = document.createElement('td');
      const descMain = document.createElement('div');
      descMain.className = 'fw-medium transaction-description-cell';
      descMain.textContent = t.description;
      descMain.title = t.description || '';
      tdDesc.appendChild(descMain);

      // Debit (right aligned)
      const tdDebit = document.createElement('td');
      tdDebit.className = 'text-end font-tabular text-danger';
      tdDebit.textContent = t.debit ? formatINR(t.debit) : '—';

      // Credit (right aligned)
      const tdCredit = document.createElement('td');
      tdCredit.className = 'text-end font-tabular text-success';
      tdCredit.textContent = t.credit ? formatINR(t.credit) : '—';

      // Balance (right aligned)
      const tdBal = document.createElement('td');
      tdBal.className = 'text-end font-tabular';
      tdBal.textContent = t.balance ? formatINR(t.balance) : '—';

      // Category select (inline correction)
      const tdCat = document.createElement('td');
      tdCat.addEventListener('click', (e) => e.stopPropagation());

      const select = document.createElement('select');
      select.className = 'form-select form-select-sm';
      if (!t.category_id) {
        const unclassified = document.createElement('option');
        unclassified.value = '';
        unclassified.textContent = 'Unclassified';
        unclassified.selected = true;
        select.appendChild(unclassified);
      }
      categoriesList.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name;
        if (c.id === t.category_id) opt.selected = true;
        select.appendChild(opt);
      });

      select.addEventListener('change', async () => {
        const prevId = t.category_id;
        const newCatId = select.value;
        try {
          await apiRequest(`/api/transactions/${t.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ category_id: newCatId }),
          });
          showToast('Category updated (manual override).', 'success');
          t.category_id = newCatId;
          t.manual_override = true;
          t.classification_method = 'manual';
          renderMethodBadge(tdMethod, t);
        } catch (err) {
          select.value = prevId; // rollback
        }
      });
      tdCat.appendChild(select);

      // Method & Confidence badge
      const tdMethod = document.createElement('td');
      renderMethodBadge(tdMethod, t);
      if (t.needs_review && t.category_id) {
        const confirmButton = document.createElement('button');
        confirmButton.type = 'button';
        confirmButton.className = 'btn btn-sm btn-outline-success ms-2';
        confirmButton.setAttribute('aria-label', 'Confirm category and resolve review');
        confirmButton.title = 'Confirm this category is correct';
        const checkIcon = document.createElement('i');
        checkIcon.className = 'bi bi-check-lg';
        confirmButton.appendChild(checkIcon);
        confirmButton.addEventListener('click', async (event) => {
          event.stopPropagation();
          confirmButton.disabled = true;
          try {
            await apiRequest(`/api/transactions/${t.id}`, {
              method: 'PATCH',
              body: JSON.stringify({ needs_review: false }),
            });
            t.needs_review = false;
            showToast('Transaction confirmed and removed from review.', 'success');
            await applyFilters(1);
          } catch (err) {
            confirmButton.disabled = false;
            showToast(err.message || 'Could not confirm this transaction.', 'danger');
          }
        });
        tdMethod.appendChild(confirmButton);
      }

      tr.appendChild(tdDate);
      tr.appendChild(tdDesc);
      tr.appendChild(tdDebit);
      tr.appendChild(tdCredit);
      tr.appendChild(tdBal);
      tr.appendChild(tdCat);
      tr.appendChild(tdMethod);

      // Row click opens drawer
      tr.addEventListener('click', () => openTransactionDrawer(t));

      tbody.appendChild(tr);
    });

    renderTxnPagination(data.total, data.page, data.page_size);
  } catch (err) {
    tbody.replaceChildren();
  }
}

function renderMethodBadge(container, t) {
  container.replaceChildren();
  const method = t.classification_method || 'none';

  const badge = document.createElement('span');
  if (t.manual_override || method === 'manual') {
    badge.className = 'badge bg-primary me-1';
    badge.textContent = 'Manual';
  } else if (method === 'rule') {
    badge.className = 'badge bg-info text-dark me-1';
    badge.textContent = 'Rule';
  } else if (method === 'ml') {
    badge.className = 'badge bg-secondary me-1';
    badge.textContent = 'ML';
  } else {
    badge.className = 'badge bg-light text-dark border me-1';
    badge.textContent = 'None';
  }

  container.appendChild(badge);

  if (t.needs_review) {
    const reviewBadge = document.createElement('span');
    reviewBadge.className = 'badge bg-warning text-dark me-1';
    reviewBadge.textContent = 'Needs review';
    container.appendChild(reviewBadge);
  }

  // Confidence (never 100% per spec; manual/none -> '—')
  const confSpan = document.createElement('span');
  confSpan.className = 'small text-muted';
  if (t.confidence !== null && t.confidence !== undefined && method !== 'manual' && method !== 'none') {
    const pct = Math.min(Math.round(t.confidence * 100), 99);
    confSpan.textContent = `${pct}%`;
  } else {
    confSpan.textContent = '—';
  }
  container.appendChild(confSpan);
}

function openTransactionDrawer(t) {
  const drawerEl = document.getElementById('transactionDrawer');
  if (!drawerEl) return;

  const setD = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val || '—';
  };

  setD('drawerId', t.id);
  setD('drawerDate', formatDate(t.transaction_date));
  setD('drawerDesc', t.description);
  setD('drawerOrigDesc', t.original_description);
  setD('drawerDebit', t.debit ? formatINR(t.debit) : '—');
  setD('drawerCredit', t.credit ? formatINR(t.credit) : '—');
  setD('drawerBalance', t.balance ? formatINR(t.balance) : '—');
  setD('drawerRef', t.reference_number);
  setD('drawerTransactionId', t.transaction_id);
  setD('drawerMode', t.mode);
  setD('drawerMethod', t.classification_method);
  setD(
    'drawerSourcePage',
    t.source_page
      ? `Page ${t.source_page}${t.source_row ? `, row ${t.source_row}` : ''}`
      : '—',
  );
  setD(
    'drawerExtractionConfidence',
    t.extraction_confidence === null || t.extraction_confidence === undefined
      ? 'Not available'
      : `${Math.round(t.extraction_confidence * 100)}%`,
  );

  // Warnings
  const warningsList = document.getElementById('drawerWarningsList');
  if (warningsList) {
    warningsList.replaceChildren();
    if (t.warnings && t.warnings.length > 0) {
      t.warnings.forEach(w => {
        const li = document.createElement('li');
        li.className = 'text-warning';
        li.textContent = w;
        warningsList.appendChild(li);
      });
    } else {
      const li = document.createElement('li');
      li.className = 'text-muted';
      li.textContent = 'None';
      warningsList.appendChild(li);
    }
  }

  // Anomalies
  const anomalyList = document.getElementById('drawerAnomalyList');
  if (anomalyList) {
    anomalyList.replaceChildren();
    if (t.anomaly_flags && t.anomaly_flags.length > 0) {
      t.anomaly_flags.forEach(a => {
        const li = document.createElement('li');
        li.className = 'text-danger';
        li.textContent = `${a.type}: ${a.detail}`;
        anomalyList.appendChild(li);
      });
    } else {
      const li = document.createElement('li');
      li.className = 'text-muted';
      li.textContent = 'No anomaly flags';
      anomalyList.appendChild(li);
    }
  }

  // Notes editing
  const notesInput = document.getElementById('drawerNotesInput');
  if (notesInput) {
    notesInput.value = t.notes || '';
  }

  const saveNotesBtn = document.getElementById('drawerSaveNotesBtn');
  if (saveNotesBtn) {
    saveNotesBtn.onclick = async () => {
      try {
        await apiRequest(`/api/transactions/${t.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ notes: notesInput.value }),
        });
        showToast('Notes saved.', 'success');
        t.notes = notesInput.value;
      } catch (err) {}
    };
  }

  const bsOffcanvas = new bootstrap.Offcanvas(drawerEl);
  bsOffcanvas.show();
}

function renderTxnPagination(total, page, pageSize) {
  const container = document.getElementById('txnPagination');
  if (!container) return;
  container.replaceChildren();

  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return;

  const ul = document.createElement('ul');
  ul.className = 'pagination pagination-sm mb-0';

  for (let i = 1; i <= Math.min(totalPages, 10); i++) {
    const li = document.createElement('li');
    li.className = `page-item ${i === page ? 'active' : ''}`;
    const btn = document.createElement('button');
    btn.className = 'page-link';
    btn.textContent = i;
    btn.addEventListener('click', () => applyFilters(i));
    li.appendChild(btn);
    ul.appendChild(li);
  }

  container.appendChild(ul);
}
