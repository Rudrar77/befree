/**
 * Chart.js controller for financial dashboard visualizations.
 * Note: Number() is ONLY used at the final chart rendering step;
 * tooltips display the original formatted string.
 */

import { apiRequest } from './api.js';
import { formatDate } from './dates.js';
import { formatINR } from './money.js';

let categoryChart = null;
let monthlyChart = null;
let distributionChart = null;
let dailyChart = null;

export async function loadDashboardAnalytics(statementId = null) {
  const endpoint = statementId ? `/api/analytics/${statementId}` : '/api/analytics';
  try {
    const [data, recent] = await Promise.all([
      apiRequest(endpoint),
      statementId
        ? Promise.resolve(null)
        : apiRequest('/api/dashboard/recent-transactions'),
    ]);
    updateDashboardCards(data);
    renderCharts(data);
    if (recent) renderRecentTransactions(recent);
  } catch (err) {
    showDashboardNotice(err.message || 'Could not load dashboard data.', 'danger');
    throw err;
  }
}

function updateDashboardCards(data) {
  const setCard = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = formatINR(val);
  };

  setCard('totalIncomeCard', data.total_income);
  setCard('totalExpensesCard', data.total_expenses);
  setCard('netCashFlowCard', data.net_cash_flow);
  setCard('transfersInCard', data.transfers_in);
  setCard('transfersOutCard', data.transfers_out);

  const unclassifiedEl = document.getElementById('unclassifiedCountCard');
  if (unclassifiedEl) {
    unclassifiedEl.textContent = data.unclassified_count || 0;
  }
}

function renderRecentTransactions(data) {
  const tbody = document.getElementById('dashboardRecentTransactions');
  if (!tbody) return;
  tbody.replaceChildren();

  if (!data.items?.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 9;
    cell.className = 'text-center py-4 text-muted';
    cell.textContent = 'No transactions from processed PDFs yet. Upload and process a bank statement to see its extracted transactions here.';
    row.appendChild(cell);
    tbody.appendChild(row);
    showDashboardNotice('', 'secondary', true);
    return;
  }

  data.items.forEach(transaction => {
    const row = document.createElement('tr');
    const date = document.createElement('td');
    date.textContent = formatDate(transaction.transaction_date);

    const description = document.createElement('td');
    description.textContent = transaction.description || '—';
    description.className = 'transaction-description-cell';
    description.title = transaction.description || '';

    const statementCell = document.createElement('td');
    const statementLink = document.createElement('a');
    statementLink.href = `/statements/${transaction.statement_id}`;
    statementLink.textContent = transaction.statement_filename || 'Statement';
    statementLink.title = transaction.statement_bank_name || '';
    statementCell.appendChild(statementLink);

    const category = document.createElement('td');
    const categoryBadge = document.createElement('span');
    categoryBadge.className = 'badge bg-light text-dark border';
    categoryBadge.textContent = transaction.category_name || 'Unclassified';
    if (transaction.category_color) {
      categoryBadge.style.borderColor = transaction.category_color;
      categoryBadge.style.borderLeftWidth = '4px';
    }
    category.appendChild(categoryBadge);

    const classification = document.createElement('td');
    const methodBadge = document.createElement('span');
    methodBadge.className = `badge ${transaction.classification_method === 'rule' ? 'bg-info text-dark' : transaction.classification_method === 'ml' ? 'bg-primary' : 'bg-secondary'}`;
    methodBadge.textContent = transaction.classification_method || 'none';
    classification.appendChild(methodBadge);
    if (transaction.confidence !== null && transaction.confidence !== undefined) {
      const confidence = document.createElement('div');
      confidence.className = 'small text-muted';
      confidence.textContent = `${Math.round(transaction.confidence * 100)}% confidence`;
      classification.appendChild(confidence);
    }

    const review = document.createElement('td');
    const reviewBadge = document.createElement('span');
    reviewBadge.className = `badge ${transaction.needs_review ? 'bg-warning text-dark' : 'bg-success'}`;
    reviewBadge.textContent = transaction.needs_review ? 'Review' : 'OK';
    review.appendChild(reviewBadge);

    const debit = document.createElement('td');
    debit.className = 'text-end text-danger font-tabular';
    debit.textContent = transaction.debit ? formatINR(transaction.debit) : '—';

    const credit = document.createElement('td');
    credit.className = 'text-end text-success font-tabular';
    credit.textContent = transaction.credit ? formatINR(transaction.credit) : '—';

    const balance = document.createElement('td');
    balance.className = 'text-end font-tabular';
    balance.textContent = transaction.balance ? formatINR(transaction.balance) : '—';

    row.append(date, description, statementCell, category, classification, review, debit, credit, balance);
    tbody.appendChild(row);
  });
  showDashboardNotice('', 'secondary', true);
}

function showDashboardNotice(message, type = 'secondary', hidden = false) {
  const notice = document.getElementById('dashboardDataNotice');
  if (!notice) return;
  notice.className = `alert alert-${type} m-3 mb-0${hidden ? ' d-none' : ''}`;
  notice.textContent = message;
}

function renderCharts(data) {
  renderCategoryChart(data.category_expenditure || []);
  renderMonthlyChart(data.monthly || []);
  renderDistributionChart(data.debit_credit_distribution || {});
  renderDailyChart(data.daily_transaction_counts || []);
}

function renderCategoryChart(categories) {
  const canvas = document.getElementById('categoryExpenditureChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (categoryChart) categoryChart.destroy();

  const labels = categories.map(c => c.category_name);
  const values = categories.map(c => Number(c.total));
  const rawStrings = categories.map(c => c.total);
  const palette = [
    '#EF4444', '#F59E0B', '#8B5CF6', '#10B981', '#3B82F6',
    '#EC4899', '#F97316', '#DC2626', '#78716C', '#14B8A6', '#6366F1',
  ];

  categoryChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: categories.map((category, index) => (
          category.color || palette[index % palette.length]
        )),
      }],
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: {
          callbacks: {
            label: function(context) {
              const idx = context.dataIndex;
              return `${labels[idx]}: ${formatINR(rawStrings[idx])}`;
            },
          },
        },
      },
    },
  });
}

function renderMonthlyChart(monthly) {
  const canvas = document.getElementById('monthlyCashFlowChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (monthlyChart) monthlyChart.destroy();

  const labels = monthly.map(m => m.month);
  const incomes = monthly.map(m => Number(m.income));
  const expenses = monthly.map(m => Number(m.expenses));

  monthlyChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Income',
          data: incomes,
          backgroundColor: '#10B981',
        },
        {
          label: 'Expenses',
          data: expenses,
          backgroundColor: '#EF4444',
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: {
          callbacks: {
            label: function(context) {
              const val = context.raw;
              return `${context.dataset.label}: ${formatINR(String(val))}`;
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
        },
      },
    },
  });
}

function renderDistributionChart(dist) {
  const canvas = document.getElementById('debitCreditDistributionChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (distributionChart) distributionChart.destroy();

  const labels = ['Debits', 'Credits'];
  const dataCounts = [dist.debit_count || 0, dist.credit_count || 0];

  distributionChart = new Chart(canvas, {
    type: 'pie',
    data: {
      labels,
      datasets: [{
        data: dataCounts,
        backgroundColor: ['#EF4444', '#10B981'],
      }],
    },
    options: {
      responsive: true,
    },
  });
}

function renderDailyChart(daily) {
  const canvas = document.getElementById('dailyCountsChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (dailyChart) dailyChart.destroy();

  const labels = daily.map(d => d.date);
  const counts = daily.map(d => d.count);

  dailyChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Transaction Count',
        data: counts,
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.2,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { stepSize: 1 },
        },
      },
    },
  });
}
