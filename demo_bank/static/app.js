async function loadBalances() {
  const list = document.querySelector('[data-testid="product-list"]');
  const loading = document.querySelector('[data-testid="balances-loading"]');
  if (!list) return;

  const response = await fetch('/api/products');
  if (!response.ok) {
    if (loading) loading.textContent = 'Не удалось загрузить остатки';
    return;
  }

  const { products } = await response.json();
  for (const product of products) {
    const item = list.querySelector(`[data-product-id="${product.product_id}"]`);
    if (!item) continue;
    const cell = item.querySelector('[data-testid="product-balance"]');
    cell.textContent = product.balance;
    cell.removeAttribute('data-balance-pending');
    if (product.available_balance) {
      const extra = document.createElement('span');
      extra.setAttribute('data-testid', 'product-available');
      extra.textContent = product.available_balance;
      item.appendChild(extra);
    }
  }
  if (loading) loading.remove();
}

async function loadMoreTransactions(button) {
  const table = document.querySelector('[data-testid="tx-table"]');
  const body = document.getElementById('tx-body');
  const params = new URLSearchParams({
    date_from: table.dataset.dateFrom,
    date_to: table.dataset.dateTo,
    cursor: button.dataset.cursor,
  });

  button.disabled = true;
  const response = await fetch(`/api/products/${table.dataset.productId}/transactions?${params}`);
  const { items, next_cursor } = await response.json();

  for (const tx of items) {
    const row = document.createElement('tr');
    row.setAttribute('data-testid', 'tx-row');
    row.dataset.txId = tx.id;
    row.innerHTML =
      `<td data-testid="tx-operation-date">${tx.operation_date}</td>` +
      `<td data-testid="tx-posting-date">${tx.posting_date || ''}</td>` +
      `<td data-testid="tx-amount">${tx.amount}</td>` +
      `<td data-testid="tx-currency">${tx.currency}</td>` +
      `<td data-testid="tx-description">${tx.description}</td>` +
      `<td data-testid="tx-counterparty">${tx.counterparty || ''}</td>` +
      `<td data-testid="tx-category">${tx.category || ''}</td>` +
      `<td data-testid="tx-status">${tx.status}</td>`;
    body.appendChild(row);
  }

  if (next_cursor === null) button.remove();
  else {
    button.dataset.cursor = next_cursor;
    button.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadBalances();
  const more = document.querySelector('[data-testid="load-more"]');
  if (more) more.addEventListener('click', () => loadMoreTransactions(more));
});
