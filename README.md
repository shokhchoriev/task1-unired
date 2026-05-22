# Unired Transfer System

Django + Celery + Redis asosidagi JSON-RPC 2.0 pul o'tkazma platformasi.

## Tizim tarkibi

| App | Vazifasi |
|-----|---------|
| `cards` | Karta modeli, Excel/CSV import, Django admin |
| `task2` | JSON-RPC 2.0 transfer API |
| `tgbot` | Telegram bot integratsiya |
| `config` | Celery, Redis, logging sozlamalari |

---

## O'rnatish

### 1. Virtual muhit va paketlar

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Muhit o'zgaruvchilari

`.env` fayl yarating:

```env
REDIS_URL=redis://127.0.0.1:6379
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_REPORT_CHAT_ID=your_chat_id_here
```

### 3. Ma'lumotlar bazasi

```bash
python manage.py migrate
python manage.py createsuperuser
```

---

## Servislarni ishga tushirish

Har birini alohida terminal oynasida ishga tushiring:

```bash
# 1. Redis (brew yoki system package orqali o'rnatilgan bo'lishi kerak)
redis-server

# 2. Django development server
python manage.py runserver

# 3. Celery worker (vazifalarni bajaruvchi)
celery -A config worker -l info

# 4. Celery beat (vaqt jadvalini boshqaruvchi)
celery -A config beat -l info
```

---

## API — Endpoint jadvali

Barcha so'rovlar `POST /task2/` ga `Content-Type: application/json` bilan yuboriladi.

**JSON-RPC 2.0 format:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method.name",
  "params": { ... }
}
```

### card.info

Karta ma'lumotlarini qaytaradi. Natija Redis da **60 soniya** cache qilinadi.

```json
// Request
{
  "method": "card.info",
  "params": {
    "card_number": "8600123412341234",
    "expiry": "12/26"
  }
}

// Success response
{
  "result": {
    "card_status": "active",
    "balance": "1500000.00",
    "phone": "+998901234567",
    "masked_card": "860012******1234"
  }
}
```

### transfer.create

Yangi o'tkazma yaratadi va OTP kodni SMS + Telegram orqali yuboradi.

```json
// Request
{
  "method": "transfer.create",
  "params": {
    "ext_id": "tr-1716371234567",
    "sender_card_number": "8600123412341234",
    "sender_card_expiry": "12/26",
    "receiver_card_number": "8600567856785678",
    "sending_amount": 50000,
    "currency": 860
  }
}

// Success response
{
  "result": {
    "ext_id": "tr-1716371234567",
    "state": "created",
    "otp_sent": true
  }
}
```

### transfer.confirm

OTP kodni tekshirib, balanslarni atomik yangilaydi.

```json
// Request
{
  "method": "transfer.confirm",
  "params": {
    "ext_id": "tr-1716371234567",
    "otp": "847291"
  }
}

// Success response
{ "result": { "ext_id": "tr-1716371234567", "state": "confirmed" } }
```

### transfer.cancel

Faqat `state=created` bo'lgan o'tkazmani bekor qiladi.

```json
// Request
{ "method": "transfer.cancel", "params": { "ext_id": "tr-1716371234567" } }

// Success response
{ "result": { "state": "cancelled" } }
```

### transfer.state

O'tkazma holatini qaytaradi.

```json
// Request
{ "method": "transfer.state", "params": { "ext_id": "tr-1716371234567" } }

// Response
{ "result": { "ext_id": "tr-1716371234567", "state": "confirmed" } }
```

### transfer.history

Filtrlar bilan o'tkazmalar ro'yxatini qaytaradi.

```json
// Request
{
  "method": "transfer.history",
  "params": {
    "card_number": "8600123412341234",
    "start_date": "2026-05-01",
    "end_date": "2026-05-22",
    "status": "confirmed"
  }
}

// Response
{
  "result": [
    {
      "ext_id": "tr-001",
      "sending_amount": "50000.00",
      "state": "confirmed",
      "created_at": "2026-05-22T14:30:01"
    }
  ]
}
```

---

## Xato kodlari

| Kod | Sabab |
|-----|-------|
| 32700 | ext_id format noto'g'ri |
| 32701 | ext_id allaqachon mavjud |
| 32702 | Balans yetarli emas |
| 32703 | Kartaga telefon raqami bog'lanmagan |
| 32704 | Karta topilmadi yoki muddati o'tgan |
| 32705 | Karta faol emas |
| 32706 | Noma'lum xato |
| 32707 | Valyuta ruxsat etilmagan (faqat 643, 840) |
| 32708 | Summa juda katta |
| 32709 | Summa juda kichik (≤ 0) |
| 32710 | OTP muddati o'tgan (transfer created emas) |
| 32711 | OTP urinishlar chegarasi (3 ta) oshdi |
| 32712 | Noto'g'ri OTP |

---

## Caching (Redis)

Redis **DB 1** ishlatiladi (`REDIS_URL/1`).

| Cache key | TTL | Maqsad |
|-----------|-----|--------|
| `card_info:{card_number}:{expiry}` | 60s | card.info natijasi |
| `error_msg:{code}` | 300s | Error model yozuvlari |
| `_rate_cache` (in-memory) | 3600s | CBU valyuta kurslari |

---

## Logging

Barcha loglar `logs/` papkasiga yoziladi.

| Fayl | Logger | Nima yoziladi |
|------|--------|---------------|
| `logs/request.log` | `task2.request` | Har bir RPC so'rov/javob + IP |
| `logs/error.log` | `task2.error` | Faqat exception va xatolar |

**Format:** `YYYY-MM-DD HH:MM:SS | LEVEL | logger | message`

**Decorator:** `@log_transfer_method` barcha transfer metodlariga timing va payload logini qo'shadi.

---

## Periodic Tasks (Celery Beat)

| Task | Jadval (dev) | Jadval (prod) | Maqsad |
|------|-------------|---------------|--------|
| `send_hourly_report` | har 60s | har soat | Karta + transfer statistikasi → Telegram |
| `send_daily_report` | — | har kunda | Kunlik to'liq hisobot → Telegram |

Hisobot Telegram guruhiga `TELEGRAM_REPORT_CHAT_ID` ga yuboriladi.

---

## Cards App (Task 1)

### Sample fayllar

```
data/cards_sample.xlsx
data/cards_sample.csv
```

### Admin import

1. `/admin/` ga kiring
2. `Cards → Cards` → `Import Excel/CSV`
3. Fayl yuklang — noto'g'ri qatorlar warning sifatida ko'rsatiladi

### Export command

```bash
python manage.py export_cards --output cards_export.csv
python manage.py export_cards --status active --output active_cards.csv
python manage.py export_cards --card-number "8600 1234 5678 9012" --output one_card.csv
python manage.py export_cards --phone "99 973 03 03" --output by_phone.csv
```

### Fake messaging command

```bash
python manage.py send_fake_messages --status active
python manage.py send_fake_messages --phone "99 973 03 03" --chat-id 12345
python manage.py send_fake_messages --card-number "8600 1234 5678 9012" --lang UZ
```

---

## Hujjatlar

| Resurs | Joylashuv |
|--------|-----------|
| Arxitektura diagrammasi | `docs/diagrams/transfer_flow.drawio` |
| Postman collection | `docs/postman/task2_collection.json` |
| Postman environment | `docs/postman/task2_environment.json` |
| Biznes qo'llanma | `docs/business_guide.html` |
