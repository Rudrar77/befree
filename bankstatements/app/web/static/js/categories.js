/**
 * Category and classification rule management controller.
 */

import { apiRequest, showToast } from './api.js';

let categories = [];
let rules = [];

export async function initCategoriesView() {
  await loadCategories();
  await loadRules();
  setupCategoryModal();
  setupRuleModal();
}

async function loadCategories() {
  const container = document.getElementById('categoriesListContainer');
  if (!container) return;

  try {
    const data = await apiRequest('/api/categories');
    categories = data.items || [];
    container.replaceChildren();

    categories.forEach(cat => {
      const card = document.createElement('div');
      card.className = 'col-md-4 col-sm-6 mb-3';

      const inner = document.createElement('div');
      inner.className = 'card h-100 shadow-sm border-start border-4';
      inner.style.borderLeftColor = cat.color || '#6B7280';

      const body = document.createElement('div');
      body.className = 'card-body d-flex justify-content-between align-items-center';

      const info = document.createElement('div');
      const name = document.createElement('h6');
      name.className = 'mb-1';
      name.textContent = cat.name;

      const badges = document.createElement('div');
      if (cat.is_system) {
        const sysBadge = document.createElement('span');
        sysBadge.className = 'badge bg-secondary me-1';
        sysBadge.textContent = 'System';
        badges.appendChild(sysBadge);
      }
      if (cat.is_transfer) {
        const trBadge = document.createElement('span');
        trBadge.className = 'badge bg-info text-dark';
        trBadge.textContent = 'Transfer';
        badges.appendChild(trBadge);
      }

      info.appendChild(name);
      info.appendChild(badges);

      body.appendChild(info);

      // Only custom categories can be edited
      if (!cat.is_system) {
        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn-sm btn-outline-secondary';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', () => openEditCategoryModal(cat));
        body.appendChild(editBtn);
      }

      inner.appendChild(body);
      card.appendChild(inner);
      container.appendChild(card);
    });

    populateRuleCategorySelect();
  } catch (err) {
    showToast(err.message || 'Could not load categories.', 'danger');
  }
}

async function loadRules(categoryId = null) {
  const tbody = document.getElementById('rulesTableBody');
  if (!tbody) return;

  try {
    const url = categoryId ? `/api/categories/rules?category_id=${categoryId}` : '/api/categories/rules';
    const data = await apiRequest(url);
    rules = data.items || [];
    tbody.replaceChildren();

    if (rules.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 7;
      td.className = 'text-center text-muted py-3';
      td.textContent = 'No classification rules found.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    rules.forEach(rule => {
      const tr = document.createElement('tr');

      const tdKw = document.createElement('td');
      tdKw.className = 'fw-bold';
      tdKw.textContent = rule.keyword;

      const tdCat = document.createElement('td');
      tdCat.textContent = rule.category_name;

      const tdMatch = document.createElement('td');
      tdMatch.textContent = rule.match_type;

      const tdDir = document.createElement('td');
      tdDir.textContent = rule.direction || 'any';

      const tdPrio = document.createElement('td');
      tdPrio.textContent = rule.priority;

      const tdType = document.createElement('td');
      const typeBadge = document.createElement('span');
      typeBadge.className = `badge bg-${rule.is_user_defined ? 'primary' : 'secondary'}`;
      typeBadge.textContent = rule.is_user_defined ? 'User' : 'System';
      tdType.appendChild(typeBadge);

      const tdActions = document.createElement('td');
      tdActions.className = 'text-end';

      if (rule.is_user_defined) {
        const delBtn = document.createElement('button');
        delBtn.className = 'btn btn-sm btn-outline-danger';
        delBtn.textContent = 'Delete';
        delBtn.addEventListener('click', async () => {
          if (confirm(`Delete rule '${rule.keyword}'?`)) {
            try {
              await apiRequest(`/api/categories/rules/${rule.id}`, { method: 'DELETE' });
              showToast('Rule deleted.', 'success');
              loadRules();
            } catch (err) {}
          }
        });
        tdActions.appendChild(delBtn);
      } else {
        tdActions.textContent = '—';
      }

      tr.appendChild(tdKw);
      tr.appendChild(tdCat);
      tr.appendChild(tdMatch);
      tr.appendChild(tdDir);
      tr.appendChild(tdPrio);
      tr.appendChild(tdType);
      tr.appendChild(tdActions);

      tbody.appendChild(tr);
    });
  } catch (err) {}
}

function populateRuleCategorySelect() {
  const sel = document.getElementById('ruleCategorySelect');
  if (!sel) return;
  sel.replaceChildren();

  categories.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name;
    sel.appendChild(opt);
  });
}

function setupCategoryModal() {
  const saveBtn = document.getElementById('saveCategoryBtn');
  if (!saveBtn) return;

  saveBtn.addEventListener('click', async () => {
    const nameInput = document.getElementById('categoryNameInput');
    const transferCheck = document.getElementById('categoryTransferCheck');
    const colorInput = document.getElementById('categoryColorInput');

    const name = nameInput?.value?.trim();
    if (!name) {
      showToast('Category name cannot be empty.', 'warning');
      return;
    }

    try {
      const categoryId = saveBtn.dataset.categoryId;
      const payload = {
        name,
        is_transfer: Boolean(transferCheck?.checked),
        color: colorInput?.value || '#6B7280',
      };
      await apiRequest(
        categoryId ? `/api/categories/${categoryId}` : '/api/categories',
        {
          method: categoryId ? 'PATCH' : 'POST',
          body: JSON.stringify(payload),
        },
      );

      showToast(
        categoryId ? `Category '${name}' updated.` : `Category '${name}' created.`,
        'success',
      );
      saveBtn.dataset.categoryId = '';
      bootstrap.Modal.getInstance(document.getElementById('categoryModal'))?.hide();
      nameInput.value = '';
      if (transferCheck) transferCheck.checked = false;
      if (colorInput) colorInput.value = '#6B7280';
      loadCategories();
    } catch (err) {
      showToast(err.message || 'Could not save category.', 'danger');
    }
  });

  const modal = document.getElementById('categoryModal');
  if (modal) {
    modal.addEventListener('hidden.bs.modal', () => {
      saveBtn.dataset.categoryId = '';
      const nameInput = document.getElementById('categoryNameInput');
      const transferCheck = document.getElementById('categoryTransferCheck');
      const colorInput = document.getElementById('categoryColorInput');
      if (nameInput) nameInput.value = '';
      if (transferCheck) transferCheck.checked = false;
      if (colorInput) colorInput.value = '#6B7280';
      const title = modal.querySelector('.modal-title');
      if (title?.dataset.originalText) {
        title.textContent = title.dataset.originalText;
      }
      if (saveBtn.dataset.originalText) {
        saveBtn.textContent = saveBtn.dataset.originalText;
      }
    });
  }
}

function setupRuleModal() {
  const saveBtn = document.getElementById('saveRuleBtn');
  if (!saveBtn) return;

  saveBtn.addEventListener('click', async () => {
    const catSelect = document.getElementById('ruleCategorySelect');
    const kwInput = document.getElementById('ruleKeywordInput');
    const matchSelect = document.getElementById('ruleMatchTypeSelect');
    const prioInput = document.getElementById('rulePriorityInput');

    const keyword = kwInput?.value?.trim();
    const category_id = catSelect?.value;
    const match_type = matchSelect?.value || 'partial';
    const priority = parseInt(prioInput?.value || '100', 10);

    if (!keyword || !category_id) {
      showToast('Keyword and category are required.', 'warning');
      return;
    }

    try {
      await apiRequest('/api/categories/rules', {
        method: 'POST',
        body: JSON.stringify({
          category_id,
          keyword,
          match_type,
          priority,
        }),
      });

      showToast(`Rule for '${keyword}' created.`, 'success');
      bootstrap.Modal.getInstance(document.getElementById('ruleModal'))?.hide();
      kwInput.value = '';
      loadRules();
    } catch (err) {}
  });
}

function openEditCategoryModal(cat) {
  const modal = document.getElementById('categoryModal');
  const saveBtn = document.getElementById('saveCategoryBtn');
  const nameInput = document.getElementById('categoryNameInput');
  const transferCheck = document.getElementById('categoryTransferCheck');
  const colorInput = document.getElementById('categoryColorInput');
  if (!modal || !saveBtn || !nameInput || !transferCheck || !colorInput) return;

  saveBtn.dataset.categoryId = cat.id;
  if (!saveBtn.dataset.originalText) {
    saveBtn.dataset.originalText = saveBtn.textContent || '';
  }
  if (saveBtn.textContent) saveBtn.textContent = 'Save Changes';
  nameInput.value = cat.name || '';
  transferCheck.checked = Boolean(cat.is_transfer);
  colorInput.value = cat.color || '#6B7280';

  const title = modal.querySelector('.modal-title');
  if (title) {
    if (!title.dataset.originalText) {
      title.dataset.originalText = title.textContent || '';
    }
    title.textContent = 'Edit Category';
  }

  bootstrap.Modal.getOrCreateInstance(modal).show();
}
