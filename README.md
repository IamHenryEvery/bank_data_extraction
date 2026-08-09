# bank-extractor

Прототип извлечения комплексной банковской выписки после того, как клиент сам
авторизовался в личном кабинете банка в браузере.

Решение определяет доступные продукты (карты, счета, вклады, кредиты), собирает по
каждому операции за выбранный период, приводит их к единой схеме и записывает выписку
вместе с отчётом о полноте извлечения.

Работает на собственном демо-стенде. 

---

## Требования

- [uv](https://docs.astral.sh/uv/) — через него ставится Python
- Chromium — ставить через Playwright

## Установка зависимостей

```bash
uv sync
uv run playwright install chromium
```
## Запуск
Терминал 1 — mock личного кабинета банка:

```bash
uv run uvicorn demo_bank.server:app --port 8765
```

Терминал 2 — извлечение данных:

```bash
cp config.example.yaml config.yaml
uv run python main.py config.yaml
```

Откроется браузер на странице входа демо-банка. Введите любые логин и пароль. Извлечение начинается автоматически, файлы помещаются в папку out/


### Результат 

| Файл | Содержимое |
|---|---|
| `statement.json` | выписка целиком: продукты, операции, период, согласие |
| `extraction_report.json` | отчёт о полноте: статус, каналы, предупреждения, ошибки |
| `products.csv` | продукты плоской таблицей |
| `transactions.csv` | операции плоской таблицей |
| `transactions.parquet` | операции с типами: даты `date32`, суммы `decimal128(18,2)` |

---

## Архитектура и подход

Слои идут строго один за другим, каждый следующий не знает, откуда пришли данные:

```
согласие → браузерная сессия → адаптер банка (3 канала) → нормализация
        → сборка моделей → кросс-проверки → экспорт + отчёт
```

| Слой | Модуль | Ответственность |
|---|---|---|
| Согласие | `consent.py` | скоупы, срок, границы периода |
| Сессия | `browser/` | подключение к браузеру, ожидание входа клиента |
| Адаптер | `adapters/demo_bank/` | где брать данные и в каком порядке |
| Нормализация | `normalization/` | даты, суммы, валюты, статусы, типы |
| Сборка | `normalization/normalizer.py` | сырые строки → модели схемы |
| Валидация | `validation/checks.py` | сквозные проверки собранной выписки |
| Экспорт | `export/` | JSON, CSV, Parquet |
| Оркестрация | `extraction/runner.py` | фолбэк каналов, частичные отказы, отчёт |

### Как подключается браузерная сессия

Два режима, выбираются в `config.yaml`.

| Режим | Что делает |
|---|---|
| `launch` | поднимает свой браузер с постоянным профилем и ждёт, пока клиент войдёт |
| `attach` | подключается по CDP к уже запущенному браузеру |
| `auto` | пробует `attach`, при неудаче уходит в `launch` |

Для `attach` браузер должен быть запущен с отладочным портом:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/bank-profile
```

### Как ищутся страницы и элементы

Все селекторы и пути кабинета собраны в одном файле — `adapters/demo_bank/selectors.py`.
Смена вёрстки банка правится там и только там.

Приоритет выбора: `data-testid` → роль и текст → класс. Индексы колонок не используются
принципиально: в таблице операций демо-банка заголовков меньше, чем колонок, — так
сделано намеренно, чтобы адаптер, который считает столбцы по порядку, сломался сразу.
Ожидания везде по факту появления данных, а не по времени: `wait_for_selector`,
`wait_for_function`.

### Как обрабатываются разные форматы данных

Три канала, в порядке приоритета. Если канал не справился — пробуется следующий,
и так по каждому продукту отдельно.

| Канал | Что делает |
|---|---|
| `api` | JSON-эндпоинты кабинета через `page.request` |
| `export` | нажимает «Скачать CSV» и разбирает файл |
| `dom` | читает таблицу и дожимает «Показать ещё» |

Запросы канала `api` идут через тот же браузерный контекст, то есть с уже выданными клиенту cookies. 

**Каналы ничего не парсят.** Дата остаётся `15.06.2026`, сумма `-4 919,58` с неразрывным пробелом, статус — русским словом. Разбор — работа нормализации, поэтому один нормализатор обслуживает все три канала и все будущие банки.

Нормализация умеет:

- даты — ISO, `дд.мм.гггг`, `дд/мм/гг`, «10 июня 2026 г.», «вчера»;
- суммы — `1 450,50`, `1,450.50`, `(434,63)` в скобках, типографский минус, символы валют;
- валюты — по словарю и по коду ISO-4217;
- статусы, типы и категории — по словарю банка.

**Порядок дат объявляет адаптер** `06.10.2026` — это 6 октября для
русского кабинета и 10 июня для американского
Незнакомые значения ведут себя по-разному:
- **дата операции, сумма, валюта продукта** — без них запись бессмысленна, поэтому она уходит в `rejected` с причиной и сырым значением;
- **статус, тип, категория, дата обработки** — деградируют до значения по умолчанию с предупреждением, запись сохраняется.

### Масштабирование на несколько банков

Банк добавляется новым пакетом в `adapters/` и одной строкой регистрации.
**Что нужно написать для нового банка**

```
adapters/newbank/
├── selectors.py   селекторы и пути кабинета
├── api.py         канал JSON API      — если он у банка есть
├── export.py      канал выгрузки      — если она есть
├── dom.py         канал разбора HTML  — всегда нужен
└── adapter.py     что и в каком порядке пробовать
```

```python
class NewBankAdapter:
    name = "newbank"
    date_order: DateOrder = "dmy"
    dialect: Dialect = RU
    product_channels = (Channel.API, Channel.DOM) # набор и приоритет каналов для продуктов
    transaction_channels = (Channel.API, Channel.EXPORT, Channel.DOM) # набор и приоритет каналов для транзакций
```

```python
# adapters/__init__.py
register(NewBankAdapter())
```

После этого банк выбирается в конфиге по имени: `bank: newbank`.
**Контракт проверяется типами.** `BankAdapter` — это `Protocol`, и `register()`
принимает только то, что ему соответствует. Адаптер без объявленного `date_order` или с неверной сигнатурой канала не пройдёт mypy на строке регистрации.

**Словарь языка переиспользуется.** `RU` из `normalization/dialects.py` берётся
как есть, а особенности конкретного банка накладываются поверх, не трогая общий:

```python
dialect = RU.extend(statuses={"выполнено": TransactionStatus.POSTED})
```
---

## Схема выходных данных

### `statement.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Statement",
  "type": "object",
  "required": ["bank", "extracted_at", "period"],
  "additionalProperties": false,
  "properties": {
    "bank": { "type": "string", "description": "имя адаптера банка" },
    "extracted_at": { "type": "string", "format": "date-time" },
    "period": { "$ref": "#/$defs/Period" },
    "consent": { "oneOf": [{ "$ref": "#/$defs/ConsentSummary" }, { "type": "null" }] },
    "products": { "type": "array", "items": { "$ref": "#/$defs/Product" }, "default": [] },
    "transactions": { "type": "array", "items": { "$ref": "#/$defs/Transaction" }, "default": [] }
  },
  "$defs": {
    "Period": {
      "type": "object",
      "required": ["from", "to"],
      "properties": {
        "from": { "type": "string", "format": "date" },
        "to": { "type": "string", "format": "date" }
      }
    },
    "ConsentSummary": {
      "type": "object",
      "required": ["consent_id", "scopes", "expires_at"],
      "description": "выжимка согласия: идентификатор клиента и способ получения не выгружаются",
      "properties": {
        "consent_id": { "type": "string" },
        "scopes": {
          "type": "array",
          "items": { "enum": ["products", "balances", "transactions", "requisites"] }
        },
        "expires_at": { "type": "string", "format": "date-time" }
      }
    },
    "Money": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d{2}$",
      "description": "сумма строкой с двумя знаками; расход отрицателен"
    },
    "MaskedNumber": {
      "type": "string",
      "pattern": "^\\*{4} \\d{4}$",
      "description": "иной формат схема не примет"
    },
    "Currency": { "type": "string", "pattern": "^[A-Z]{3}$", "description": "код ISO-4217" },
    "Requisites": {
      "type": "object",
      "properties": {
        "masked_account": { "oneOf": [{ "$ref": "#/$defs/MaskedNumber" }, { "type": "null" }] },
        "bic": { "type": ["string", "null"] },
        "corr_account": { "oneOf": [{ "$ref": "#/$defs/MaskedNumber" }, { "type": "null" }] },
        "bank_name": { "type": ["string", "null"] }
      }
    },
    "ProductExtractionMeta": {
      "type": "object",
      "description": "происхождение данных продукта",
      "properties": {
        "status": { "enum": ["ok", "partial", "failed"], "default": "ok" },
        "channel": { "oneOf": [{ "$ref": "#/$defs/Channel" }, { "type": "null" }] },
        "channels_tried": { "type": "array", "items": { "$ref": "#/$defs/Channel" } },
        "warnings": { "type": "array", "items": { "type": "string" } }
      }
    },
    "Channel": { "enum": ["api", "export", "dom"] },
    "Product": {
      "type": "object",
      "required": ["product_id", "type", "name", "currency"],
      "properties": {
        "product_id": { "type": "string", "description": "идентификатор в кабинете" },
        "type": { "enum": ["card", "account", "savings", "deposit", "credit"] },
        "name": { "type": "string", "description": "название как в кабинете" },
        "masked_number": { "oneOf": [{ "$ref": "#/$defs/MaskedNumber" }, { "type": "null" }] },
        "currency": { "$ref": "#/$defs/Currency" },
        "balance": { "oneOf": [{ "$ref": "#/$defs/Money" }, { "type": "null" }] },
        "available_balance": { "oneOf": [{ "$ref": "#/$defs/Money" }, { "type": "null" }] },
        "credit_limit": { "oneOf": [{ "$ref": "#/$defs/Money" }, { "type": "null" }] },
        "requisites": { "oneOf": [{ "$ref": "#/$defs/Requisites" }, { "type": "null" }] },
        "status": { "enum": ["active", "blocked", "closed", "unknown"], "default": "unknown" },
        "extraction": { "$ref": "#/$defs/ProductExtractionMeta" }
      }
    },
    "Transaction": {
      "type": "object",
      "required": [
        "transaction_id", "product_id", "operation_date",
        "amount", "currency", "description", "source_channel"
      ],
      "properties": {
        "transaction_id": {
          "type": "string",
          "description": "идентификатор банка либо синтезированный детерминированно"
        },
        "product_id": { "type": "string", "description": "ссылка на product_id продукта" },
        "operation_date": { "type": "string", "format": "date" },
        "posting_date": {
          "type": ["string", "null"],
          "format": "date",
          "description": "пусто у операций в обработке и отклонённых"
        },
        "amount": { "$ref": "#/$defs/Money" },
        "currency": { "$ref": "#/$defs/Currency" },
        "type": {
          "enum": ["purchase", "transfer", "fee", "interest", "cashback", "refund", "atm", "other"],
          "default": "other"
        },
        "description": { "type": "string", "description": "назначение как в кабинете" },
        "counterparty": { "type": ["string", "null"], "description": "контрагент или merchant" },
        "category": {
          "type": ["string", "null"],
          "description": "категория банка; незнакомая проходит как есть"
        },
        "status": { "enum": ["posted", "pending", "declined", "hold"], "default": "posted" },
        "mcc": { "type": ["string", "null"] },
        "source_channel": { "$ref": "#/$defs/Channel" }
      }
    }
  }
}
```

Три правила, общих для всей схемы:

1. **Суммы — строки, не числа.** `float` теряет точность, а числовой литерал в JSON теряет незначащий ноль: `-1450.5` вместо `-1450.50`. В Parquet — `decimal128(18,2)`.
2. **Даты — ISO**, без времени: кабинет времени операции не отдаёт.
3. **`transaction_id` при отсутствии в банке синтезируется** детерминированно из
   продукта, даты, суммы и описания — повторный прогон даст тот же идентификатор.

### Пример выписки

Ниже сокращённый фрагмент — один продукт и одна транзакция. Полная выписка со всеми пятью продуктами и 64 операциями лежит в `fixtures/golden/statement.json

```json
{
  "bank": "demo_bank",
  "extracted_at": "2026-08-09T07:12:08.234427Z",
  "period": { "from": "2026-01-01", "to": "2026-06-17" },
  "consent": {
    "consent_id": "cns_2026_0806_a17c",
    "scopes": ["products", "balances", "transactions", "requisites"],
    "expires_at": "2036-01-01T00:00:00Z"
  },
  "products": [
    {
      "product_id": "acc_002",
      "type": "account",
      "name": "Текущий счёт",
      "masked_number": "**** 4312",
      "currency": "RUB",
      "balance": "340120.00",
      "available_balance": "340120.00",
      "credit_limit": null,
      "requisites": {
        "masked_account": "**** 4312",
        "bic": "044525225",
        "corr_account": "**** 0225",
        "bank_name": "ДЕМО БАНК"
      },
      "status": "active",
      "extraction": {
        "status": "ok",
        "channel": "api",
        "channels_tried": ["api"],
        "warnings": []
      }
    }
  ],
  "transactions": [
    {
      "transaction_id": "card_001_tx_014",
      "product_id": "card_001",
      "operation_date": "2026-06-15",
      "posting_date": "2026-06-16",
      "amount": "-4919.58",
      "currency": "RUB",
      "type": "atm",
      "description": "Операция Atm 4412 Moscow",
      "counterparty": "ATM 4412 MOSCOW",
      "category": "cash",
      "status": "posted",
      "mcc": "6011",
      "source_channel": "api"
    }
  ]
}
```

### `extraction_report.json`

Пишется в любом исходе, включая фатальный: тогда `status` равен `failed`, причина лежит
в `errors`, а `session` и `consent` могут быть `null` — сессия не открылась или согласие
не успело загрузиться.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ExtractionReport",
  "type": "object",
  "required": ["run_id", "bank", "status", "period", "started_at", "finished_at", "duration_s"],
  "additionalProperties": false,
  "properties": {
    "run_id": { "type": "string", "description": "метка времени прогона" },
    "bank": { "type": "string" },
    "status": {
      "enum": ["ok", "partial", "failed"],
      "description": "partial — часть данных не извлечена; failed — не извлечено ничего"
    },
    "period": { "$ref": "#/$defs/Period" },
    "session": { "oneOf": [{ "$ref": "#/$defs/SessionInfo" }, { "type": "null" }] },
    "consent": { "oneOf": [{ "$ref": "#/$defs/ConsentSummary" }, { "type": "null" }] },
    "started_at": { "type": "string", "format": "date-time" },
    "finished_at": { "type": "string", "format": "date-time" },
    "duration_s": { "type": "number" },
    "products": { "$ref": "#/$defs/ProductsReport" },
    "transactions": { "$ref": "#/$defs/TransactionsReport" },
    "channels_used": {
      "type": "object",
      "description": "product_id → канал, которым добыты его операции",
      "additionalProperties": { "$ref": "#/$defs/Channel" }
    },
    "normalization": { "$ref": "#/$defs/NormalizationReport" },
    "validation": { "type": "array", "items": { "$ref": "#/$defs/ValidationWarning" } },
    "rejected": { "type": "array", "items": { "$ref": "#/$defs/Rejected" } },
    "errors": { "type": "array", "items": { "$ref": "#/$defs/ErrorEntry" } },
    "scope_restrictions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "что не извлекалось, потому что скоупа не было в согласии"
    }
  },
  "$defs": {
    "Channel": { "enum": ["api", "export", "dom"] },
    "Period": {
      "type": "object",
      "required": ["from", "to"],
      "properties": {
        "from": { "type": "string", "format": "date" },
        "to": { "type": "string", "format": "date" }
      }
    },
    "ConsentSummary": {
      "type": "object",
      "required": ["consent_id", "scopes", "expires_at"],
      "properties": {
        "consent_id": { "type": "string" },
        "scopes": {
          "type": "array",
          "items": { "enum": ["products", "balances", "transactions", "requisites"] }
        },
        "expires_at": { "type": "string", "format": "date-time" }
      }
    },
    "SessionInfo": {
      "type": "object",
      "required": ["mode_requested", "mode_resolved"],
      "description": "какой режим просили и какой получился: auto может стать launch",
      "properties": {
        "mode_requested": { "enum": ["attach", "launch", "auto"] },
        "mode_resolved": { "enum": ["attach", "launch"] }
      }
    },
    "ProductFailure": {
      "type": "object",
      "required": ["product_id", "reason"],
      "properties": {
        "product_id": { "type": "string" },
        "channels_tried": { "type": "array", "items": { "$ref": "#/$defs/Channel" } },
        "reason": { "type": "string" }
      }
    },
    "ProductsReport": {
      "type": "object",
      "properties": {
        "total": { "type": "integer" },
        "by_type": { "type": "object", "additionalProperties": { "type": "integer" } },
        "failed": {
          "type": "array",
          "items": { "$ref": "#/$defs/ProductFailure" },
          "description": "продукты, по которым исчерпаны все каналы"
        }
      }
    },
    "TransactionsReport": {
      "type": "object",
      "properties": {
        "total": { "type": "integer" },
        "by_product": { "type": "object", "additionalProperties": { "type": "integer" } },
        "rejected": { "type": "integer", "description": "не собрано в модель" }
      }
    },
    "WarningCount": {
      "type": "object",
      "required": ["code", "count"],
      "description": "предупреждения схлопнуты по коду, с одним образцом",
      "properties": {
        "code": { "type": "string" },
        "count": { "type": "integer" },
        "sample": { "type": ["string", "null"] }
      }
    },
    "NormalizationReport": {
      "type": "object",
      "properties": {
        "fields_total": { "type": "integer" },
        "fields_normalized": { "type": "integer" },
        "warnings": { "type": "array", "items": { "$ref": "#/$defs/WarningCount" } }
      }
    },
    "ValidationWarning": {
      "type": "object",
      "required": ["code", "message"],
      "description": "кросс-проверки собранной выписки",
      "properties": {
        "code": {
          "enum": [
            "duplicate_transaction_id", "orphan_transaction", "currency_mismatch",
            "date_outside_period", "posting_before_operation", "product_without_transactions"
          ]
        },
        "message": { "type": "string" },
        "product_id": { "type": ["string", "null"] },
        "transaction_id": { "type": ["string", "null"] }
      }
    },
    "Rejected": {
      "type": "object",
      "required": ["kind", "product_id", "reason"],
      "description": "запись, которую не удалось собрать: без этих полей она бессмысленна",
      "properties": {
        "kind": { "enum": ["product", "transaction"] },
        "product_id": { "type": "string" },
        "reason": { "type": "string" },
        "raw_value": { "type": ["string", "null"], "description": "что именно не разобралось" },
        "description": { "type": ["string", "null"] }
      }
    },
    "ErrorEntry": {
      "type": "object",
      "required": ["code", "message"],
      "properties": {
        "code": {
          "enum": [
            "channel_failed", "session_expired",
            "consent_rejected", "unknown_bank", "extraction_failed"
          ]
        },
        "message": { "type": "string" },
        "product_id": { "type": ["string", "null"] },
        "channel": { "oneOf": [{ "$ref": "#/$defs/Channel" }, { "type": "null" }] }
      }
    }
  }
}
```

---

## Сценарии демо-банка

Стенд умеет ломаться управляемо. Сценарий выбирается один раз при входе и запоминается
в куке: `http://localhost:8765/login?scenario=api_down`.

| Сценарий | Что происходит | Что демонстрирует |
|---|---|---|
| `default` | всё исправно | обычный прогон |
| `empty_history` | у `acc_002` нет операций | пустая история — не ошибка |
| `broken_formats` | три формата дат и два формата сумм вперемешку | нормализация |
| `api_down` | JSON API отдаёт 503 | фолбэк на CSV-экспорт |
| `export_down` | API и экспорт мертвы | фолбэк на DOM |
| `slow_load` | первая попытка отвечает 504 | ретраи |
| `partial_failure` | `sav_003` недоступен во всех каналах | частичный отказ, статус `partial` |
| `session_expired` | сессия истекает после трёх запросов | остановка прогона |
| `duplicate_page` | вторая страница накладывается на первую | дедупликация |
| `stuck_cursor` | сервер всегда отдаёт первую страницу | защита от зацикливания |

---


## Ограничения и риски поддержки

1. Проверено только на собственном демо-стенде. Реальный банк потребует нового адаптера, других стратегий ожидания и, скорее всего, другого поведения при переподтверждениях.
2. DOM-канал ломается при смене вёрстки. Смягчено выносом всех селекторов в один файл, но не устранено. Практический признак поломки: резкое падение числа операций при неизменном периоде — это стоит мониторить.
3. DOM-канал зависим от API. Если динамическая подгрузка кабинета ходит в тот же API, то при мёртвом API DOM не сможет добрать вторую страницу. Для историй длиннее одной страницы фолбэк в этом случае не спасает; канал честно падает вместо того, чтобы вернуть неполные данные.
4. Пропущенные операции не обнаруживаются. Дедупликация ловит задвоение, но если
страница перепрыгнула через запись, все пришедшие строки новые и заметить пропуск нечем.
5. Один язык интерфейса на банк. Диалект объявляется адаптером на уровне класса.
6. Только CSV-выгрузка.
7. Нет параллелизма. Продукты обходятся последовательно. 
8. Даты трактуются как локальные даты банка, времени операции в схеме нет.
9. Двух одинаковых операций в один день не различить, если банк не отдаёт свой идентификатор: синтетический ключ строится из продукта, даты, суммы и описания.

---

## Меры безопасности и приватности

| Мера | Где реализована |
|---|---|
| В отчёт и логи попадают только маскированные значения | `report.py`, `logging_setup.py` |
| Библиотека не вводит учётные данные ни в одно поле | тест `tests/unit/test_no_credential_input.py` |
| Схема не принимает полный номер | тип `MaskedNumber` в `models.py` |
| Логи чистятся от номеров карт и кодов | `masking.redact_text` как фильтр в `logging_setup.py` |
| Согласие со скоупами, сроком и границами периода | `consent.py`, проверка до открытия браузера |
| Без скоупа данные не запрашиваются вовсе | `runner.py`, поле `scope_restrictions` в отчёте |
| Каталог артефактов создаётся с правами `0700` | `export/__init__.py` |
| Скачанный CSV удаляется сразу после разбора | `adapters/demo_bank/export.py` |



