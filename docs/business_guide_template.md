# Unired Transfer System — Biznes Qo'llanma

> **Versiya:** 1.0 | **Sana:** 2026-05-22
> **Maqsad:** Texnik bo'lmagan foydalanuvchilar (bank menejerlari, biznes analitiklar) uchun tizimni tushuntirish.

---

## 1. Tizim nima qiladi?

Unired Transfer System — bu bank kartalaridan kartaga pul o'tkazishni amalga oshiruvchi raqamli platforma. Har bir o'tkazma SMS va Telegram orqali yuborilgan maxfiy kod (OTP) bilan tasdiqlanadi. Tizim avtomatik ravishda har soatda moliyaviy hisobotlarni tayyor qilib, belgilangan Telegram guruhiga yuboradi.

---

## 2. Asosiy modullar

| Modul | Vazifasi | Foydalanuvchi uchun nima beradi |
|-------|----------|--------------------------------|
| **Kartalar (cards)** | Barcha bank kartalarini saqlaydi va boshqaradi | Admin paneldan karta import/eksport, balans ko'rish |
| **O'tkazmalar (task2)** | Karta-dan-kartaga o'tkazma API | Pul yuborish, tasdiqlash, bekor qilish |
| **Telegram Bot (tgbot)** | OTP kodlarni va hisobotlarni yuboradi | Foydalanuvchi Telegramga OTP kodni oladi |
| **Avtomatik vazifalar (Celery)** | Har soat/kunlik statistika hisobotlari | Menejer har soat/kunda statistika oladi |

---

## 3. O'tkazma qanday ishlaydi? (oddiy til bilan)

```
1. Mijoz so'rov yuboradi
   └─► "8600-XXXX kartadan 8600-YYYY kartaga 50 000 so'm o'tkazmoqchiman"

2. Tizim tekshiradi:
   ├─ Karta bazada bormi? ✓
   ├─ Karta muddati o'tmadimi? ✓
   ├─ Telefon raqami boglanganmi? ✓
   ├─ Balans yetarlimi? ✓
   └─ Valyuta to'g'rimi? (so'm, rubl yoki dollar) ✓

3. Tasdiqlash kodi yuboriladi
   └─► Telegram va SMS ga: "🔐 OTP kodi: 847291"

4. Mijoz kodni kiritadi
   └─► Tizim mablag'ni o'tkazadi (atomik — xavfsiz)

5. Natija:
   ├─ Yuboruvchi kartadan pul ayriladi
   └─► Qabul qiluvchi kartaga pul tushadi
```

**Muhim:** OTP kodi 3 marta noto'g'ri kiritilsa, o'tkazma avtomatik bekor qilinadi.

---

## 4. Ma'lumotlar bazasi so'rovlari (texnik bo'lmagan tushuntirish)

| Amal | Tizim nima qiladi |
|------|-------------------|
| **Karta topish** | Karta raqami va muddati bo'yicha bazadan izlaydi |
| **Balans tekshirish** | Yuboruvchi balans ≥ o'tkazma summasimi? |
| **OTP tasdiqlash** | Kiritilgan kod saqlangan kod bilan mos kelishini tekshiradi |
| **Balans yangilash** | Yuboruvchidan ayiradi, qabul qiluvchiga qo'shadi (bir vaqtda, xavfsiz) |
| **Tarix ko'rish** | Barcha o'tkazmalarni sana, holat, karta raqami bo'yicha filtrlash |

---

## 5. Kesh (Cache) nima va nima uchun kerak?

Kesh — bu tez-tez so'raladigan ma'lumotlarning vaqtinchalik saqlash joyi (Redis).

| Nima saqlanadi | Qancha vaqt | Foydasi |
|----------------|-------------|---------|
| Karta ma'lumotlari (`card.info`) | 60 sekund | Har so'rovda bazaga murojaat qilmaydi |
| Xato xabarlari | 5 daqiqa | Standart xabarlar qayta o'qilmaydi |
| Valyuta kurslari (CBU) | 1 soat | Har so'rovda cbu.uz ga murojaat qilmaydi |

---

## 6. Loglar (ish jurnali) nima uchun kerak?

Tizim barcha amallarni ikki faylga yozib boradi:

**`logs/request.log`** — har bir so'rov va javob:
```
2026-05-22 14:30:01 | INFO | IP: 192.168.1.5 | Method: transfer.create | ...
2026-05-22 14:30:02 | INFO | Response: {state: "created", otp_sent: true}
```

**`logs/error.log`** — faqat xatolar:
```
2026-05-22 14:31:05 | ERROR | transfer.confirm failed: ext_id=tr-001 ...
```

**Auditorlik uchun:** Har bir o'tkazma kim, qachon, qaysi IP dan yuborilgani saqlanadi.

---

## 7. Avtomatik hisobotlar

Tizim Telegram guruhiga avtomatik hisobot yuboradi:

**Soatlik hisobot namunasi:**
```
📊 Soatlik hisobot
━━━━━━━━━━━━━━━━━━━━

💳 KARTALAR
  Jami: 1,250
  ✅ Aktiv: 980
  ⏸ Nofaol: 200
  ❌ Muddati o'tgan: 70
  💰 Umumiy balans: 45,230,000.00 UZS

🔄 O'TKAZMALAR
  Jami: 340
  ✅ Tasdiqlangan: 298 → 12,500,000.00 UZS
  ⏳ Kutilmoqda: 15 → 750,000.00 UZS
  ❌ Bekor qilingan: 27
```

---

## 8. Excel hisobotlar va import

### Karta import (Admin panel orqali)
1. `/admin/` ga kiring
2. `Cards → Cards` bo'limiga o'ting
3. `Import Excel/CSV` tugmasini bosing
4. `.xlsx` yoki `.csv` fayl yuklang

### Karta eksport (texnik buyruq)
```bash
python manage.py export_cards --output hisobot.csv
python manage.py export_cards --status active --output faol_kartalar.csv
```

---

## 9. Texnik hujjatlar

| Resurs | Tavsif |
|--------|--------|
| **Postman Collection** | API so'rovlarini sinash uchun — `docs/postman/task2_collection.json` |
| **Arxitektura diagrammasi** | Tizim oqimi — `docs/diagrams/transfer_flow.drawio` (draw.io da oching) |
| **Texnik README** | O'rnatish va ishga tushirish — `README.md` |

---

## 10. Xato kodlari jadvali

| Kod | Ma'nosi (oddiy til) | Nima qilish kerak |
|-----|---------------------|-------------------|
| 32700 | Noyob ID kerak | Boshqa ID bilan qayta yuboring |
| 32701 | Bu ID avval ishlatilgan | Yangi ID yarating |
| 32702 | Balans yetarli emas | Hisobni to'ldiring |
| 32703 | Telefon raqami bog'lanmagan | Bank bilan bog'laning |
| 32704 | Karta topilmadi yoki muddati o'tgan | Karta ma'lumotlarini tekshiring |
| 32705 | Karta faol emas | Bank bilan bog'laning |
| 32707 | Noto'g'ri valyuta | Faqat so'm (UZS), rubl (RUB) yoki dollar (USD) |
| 32710 | OTP muddati o'tgan | Yangi o'tkazma yarating |
| 32711 | OTP urinishlari tugadi | Yangi o'tkazma yarating |
| 32712 | Noto'g'ri OTP | Kodni qayta kiriting |

---

*Savollar uchun: texnik jamoa bilan bog'laning.*
