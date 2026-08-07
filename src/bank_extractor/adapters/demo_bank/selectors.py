# Все селекторы и тексты кабинета demo_bank — в одном месте: смена вёрстки
# банка правится здесь и только здесь. Приоритет выбора: сначала data-testid,
# потом роль и текст, и лишь в крайнем случае класс.

DASHBOARD_TITLE = '[data-testid="dashboard-title"]'

PRODUCT_LIST = '[data-testid="product-list"]'
PRODUCT_ITEM = '[data-testid="product-item"]'
PRODUCT_LINK = '[data-testid="product-link"]'
PRODUCT_NUMBER = '[data-testid="product-number"]'
PRODUCT_TYPE = '[data-testid="product-type"]'
PRODUCT_BALANCE = '[data-testid="product-balance"]'
PRODUCT_AVAILABLE = '[data-testid="product-available"]'
PRODUCT_CURRENCY = '[data-testid="product-currency"]'
BALANCES_LOADING = '[data-testid="balances-loading"]'
BALANCE_PENDING = "[data-balance-pending]"

PRODUCT_TITLE = '[data-testid="product-title"]'
REQUISITES = '[data-testid="requisites"]'
REQ_ACCOUNT = '[data-testid="req-account"]'
REQ_BIC = '[data-testid="req-bic"]'
REQ_CORR = '[data-testid="req-corr"]'
REQ_BANK = '[data-testid="req-bank"]'

TX_TABLE = '[data-testid="tx-table"]'
TX_ROW = '[data-testid="tx-row"]'
TX_OPERATION_DATE = '[data-testid="tx-operation-date"]'
TX_POSTING_DATE = '[data-testid="tx-posting-date"]'
TX_AMOUNT = '[data-testid="tx-amount"]'
TX_CURRENCY = '[data-testid="tx-currency"]'
TX_DESCRIPTION = '[data-testid="tx-description"]'
TX_COUNTERPARTY = '[data-testid="tx-counterparty"]'
TX_CATEGORY = '[data-testid="tx-category"]'
TX_STATUS = '[data-testid="tx-status"]'
LOAD_MORE = '[data-testid="load-more"]'
EMPTY_HISTORY = '[data-testid="empty-history"]'
EXPORT_CSV = '[data-testid="export-csv"]'

PATH_LOGIN = "/login"
PATH_DASHBOARD = "/accounts"
PATH_PRODUCT = "/accounts/{product_id}"
PATH_API_PRODUCTS = "/api/products"
PATH_API_TRANSACTIONS = "/api/products/{product_id}/transactions"
PATH_EXPORT = "/export/transactions.csv"
