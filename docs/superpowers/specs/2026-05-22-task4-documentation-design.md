# Task 4 — Documentation Design Spec

**Date:** 2026-05-22
**Approach:** Variant A — File-first (all artifacts stored in repo)

---

## Context

The project is a Django + Celery + Redis system with two main apps:

- **`cards`** — Card model, Excel/CSV import, Django admin panel
- **`task2`** — JSON-RPC 2.0 transfer API (`transfer.create`, `transfer.confirm`, `transfer.cancel`, `transfer.state`, `transfer.history`, `card.info`)
- **`tgbot`** — Telegram bot integration
- **Celery Beat** — sends hourly/daily stats to Telegram

The existing `README.md` covers only `task1` (cards app). The existing `task2_postman_collection.json` is partial. No docstrings exist in `task2/views.py` or `task2/utils.py`.

---

## Output Files

```
README.md                                    ← full rewrite
docs/
  diagrams/
    transfer_flow.drawio                     ← XML, importable in draw.io
  postman/
    task2_collection.json                    ← complete collection
    task2_environment.json                   ← Postman environment
  business_guide_template.md                 ← Google Docs template
docs/superpowers/specs/
  2026-05-22-task4-documentation-design.md  ← this file
task2/views.py                               ← docstrings added inline
task2/utils.py                               ← docstrings added inline
```

---

## 4.1 README.md

### Sections

1. **Project description** — what each app does (cards, task2, tgbot, Celery)
2. **Setup**
   - `python3 -m venv venv && pip install -r requirements.txt`
   - `.env` required variables: `REDIS_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_REPORT_CHAT_ID`
   - `python manage.py migrate && python manage.py createsuperuser`
3. **Running services**
   ```bash
   redis-server                                    # Redis
   python manage.py runserver                      # Django
   celery -A config worker -l info                 # Celery worker
   celery -A config beat -l info                   # Celery beat
   ```
4. **API endpoint summary** — table format:

   | Method           | Required params                          | Success response                      |
   |------------------|------------------------------------------|---------------------------------------|
   | `card.info`      | `card_number`, `expiry`                  | `{card_status, balance, phone, masked_card}` |
   | `transfer.create`| `ext_id`, `sender_card_number`, `sender_card_expiry`, `receiver_card_number`, `sending_amount`, `currency` | `{ext_id, state:"created", otp_sent:true}` |
   | `transfer.confirm`| `ext_id`, `otp`                         | `{ext_id, state:"confirmed"}`         |
   | `transfer.cancel`| `ext_id`                                 | `{state:"cancelled"}`                 |
   | `transfer.state` | `ext_id`                                 | `{ext_id, state}`                     |
   | `transfer.history`| `card_number?`, `start_date?`, `end_date?`, `status?` | `[{ext_id, sending_amount, state, created_at}]` |

5. **Caching** — Redis DB 1:
   - `card_info:{card_number}:{expiry}` → 60s TTL
   - `error_msg:{code}` → 300s TTL
   - CBU exchange rates (in-memory `_rate_cache`) → 3600s TTL

6. **Logging** — two log files:
   - `logs/request.log` — every request/response + IP
   - `logs/error.log` — exceptions only
   - Format: `YYYY-MM-DD HH:MM:SS | LEVEL | logger | message`

7. **Periodic tasks** (Celery Beat):
   - `send_hourly_report` — every 60s in dev (every hour in prod), sends stats to Telegram
   - `send_daily_report` — daily, full stats

8. **Error codes** — table of 327xx codes (32700–32712)

---

## 4.2 draw.io Diagram

**File:** `docs/diagrams/transfer_flow.drawio`

### Three swimlane layers

| Layer | Components |
|-------|-----------|
| **API Layer** | Client → POST /task2/ → json_rpc_view → method dispatch |
| **Business Logic** | transfer.create / transfer.confirm / transfer.cancel / card.info |
| **Infrastructure** | PostgreSQL/SQLite, Redis Cache, CBU API, Telegram Bot API, Celery |

### Transfer.create flow (main path)

```
Client → json_rpc_view
  → validate ext_id (unique) → [ERR_32701]
  → validate currency (643/840) → [ERR_32707]
  → validate amount > 0 → [ERR_32709]
  → normalize expiry format
  → Card.objects.get(sender) → [ERR_32704]
  → check sender.status == active → [ERR_32705]
  → check sender.phone exists → [ERR_32703]
  → Card.objects.get(receiver) → [ERR_32706]
  → calculate_exchange() → CBU API / fallback
  → check balance >= receiving_amount → [ERR_32702]
  → Transfer.create(state=CREATED)
  → generate_otp()
  → FakeNotificationService.send_otp → SMS + Telegram
  → Response: {state:"created", otp_sent:true}
```

### Transfer.confirm flow

```
  → Transfer.get(ext_id) → [ERR_32706]
  → state == CREATED? → [ERR_32710]
  → try_count >= 3? → cancel + [ERR_32711]
  → otp match? → try_count++ → [ERR_32712]
  → atomic: sender.balance -= receiving_amount
            receiver.balance += receiving_amount
  → Transfer.state = CONFIRMED
  → Response: {state:"confirmed"}
```

### Additional flows shown

- `card.info` → Redis cache hit/miss → DB → cache.set → Response
- `Celery Beat` → `send_hourly_report` → DB queries → Telegram

---

## 4.3 Python Docstrings

**Format:** Google style docstrings

### Target functions

#### `task2/views.py`

**`card_info(card_number, expiry)`**
- Args: `card_number` (16-digit str), `expiry` (MM/YY or YYYY-MM)
- Returns: `Success({card_status, balance, phone, masked_card})` or RPCError
- Notes: Results cached in Redis for 60s; `masked_card` shows first 6 and last 4 digits

**`transfer_create(ext_id, sender_card_number, sender_card_expiry, receiver_card_number, sending_amount, currency)`**
- Args: all typed, `currency` is ISO numeric (643=RUB, 840=USD)
- Returns: `Success({ext_id, state:"created", otp_sent:true})` or RPCError
- Side effects: creates Transfer row, sends OTP via SMS + Telegram

**`transfer_confirm(ext_id, otp)`**
- Args: `ext_id` (str), `otp` (6-digit str)
- Returns: `Success({ext_id, state:"confirmed"})` or RPCError
- Notes: uses `select_for_update()` atomic transaction; max 3 OTP attempts

**`transfer_cancel(ext_id)`**
- Args: `ext_id` (str)
- Returns: `Success({state:"cancelled"})` or RPCError
- Constraint: only `state=CREATED` transfers can be cancelled

#### `task2/utils.py`

**`log_transfer_method(func)`** — decorator
- Logs method name, payload, response, and elapsed time
- Wraps any `@method` decorated RPC handler

**`calculate_exchange(amount, currency)`**
- Args: `amount` (Decimal), `currency` (int: 643 or 840)
- Returns: UZS equivalent as Decimal
- Notes: fetches from CBU API; falls back to hardcoded rates if API fails; 1h in-memory cache

**`FakeNotificationService.send_otp(phone, tg_id, otp)`**
- Sends OTP via both SMS (logged) and Telegram Bot API
- Falls back to log-only if `TELEGRAM_BOT_TOKEN` not set

---

## 4.4 Postman Collection

**Files:**
- `docs/postman/task2_collection.json`
- `docs/postman/task2_environment.json`

### Environment variables

| Variable | Type | Value |
|----------|------|-------|
| `base_url` | string | `http://127.0.0.1:8000/task2/` |
| `ext_id` | string | auto-generated by pre-request script |
| `otp` | string | manually set after Telegram OTP delivery |
| `last_state` | string | captured from response |

### Requests

1. **`card.info`**
   - Pre-request: none
   - Test: assert `result.card_status` exists, `result.balance` is numeric string

2. **`transfer.create`**
   - Pre-request: `pm.collectionVariables.set('ext_id', 'tr-' + Date.now())`
   - Test: `state === "created"`, `otp_sent === true`, save `ext_id`

3. **`transfer.confirm`**
   - Pre-request: note that `otp` must be set manually from Telegram
   - Test: `state === "confirmed"` OR assert error code if OTP wrong

4. **`transfer.state`**
   - Test: `result.ext_id` matches saved `ext_id`

5. **`transfer.cancel`**
   - Test: `result.state === "cancelled"`

6. **`transfer.history`**
   - Test: response is array, each item has `ext_id`, `sending_amount`, `state`

### Error case tests (in every request)

```javascript
if (json.error) {
    pm.test("Error code in valid range", () => {
        pm.expect(json.error.code).to.be.within(32700, 32714);
    });
}
```

### Automated flow (Collection Runner order)

```
card.info → transfer.create → transfer.confirm → transfer.state
```

---

## 4.5 Google Docs Template

**File:** `docs/business_guide_template.md`

Non-technical audience — bank/business stakeholders.

### Sections

1. **Tizim nima qiladi?** — high-level 3 sentence description (card-to-card transfer, OTP security, automated reporting)
2. **Modullar jadvali** — cards, task2, tgbot, Celery — har birining vazifasi oddiy til bilan
3. **Ma'lumotlar bazasi so'rovlari** — "karta topish", "balans tekshirish", "OTP tasdiqlash" ni non-SQL tilda tushuntirish
4. **Loglar nima uchun kerak?** — `request.log` va `error.log` maqsadi; muammolarni aniqlash uchun ishlatilishi
5. **Excel hisobotlar** — admin panel va `export_cards` command orqali eksport qanday ishlaydi
6. **Savollar uchun havolalar** — Postman Collection, draw.io diagram, texnik jamoa kontakti

---

## Constraints & Notes

- No new features added — documentation only
- `task2/views.py` has unreachable code (lines after `transfer_cancel` return) — note it in docstring but do NOT remove
- `card.info` is in `task2/views.py` (not `cards/views.py`) — doc must reflect actual file location
- OTP in Postman flow must be entered manually (real OTP comes via Telegram, cannot be automated without bot token)
- draw.io XML will use `mxGraph` format compatible with diagrams.net
