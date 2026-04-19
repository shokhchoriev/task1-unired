# Task 1 - Django Skills

Bu loyiha quyidagilarni bajaradi:
- `Card` modeli (`card_number`, `expire`, `phone`, `status`, `balance`)
- Django admin ichida formatlangan ko'rinish va filtrlash
- Admin paneldan Excel/CSV import
- Filter bilan CSV export (`management command`)
- Filter bilan fake message yuborish (`management command`)

## 1. O'rnatish

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## 2. Sample fayl

Tayyor sample fayllar:
- `data/cards_sample.xlsx`
- `data/cards_sample.csv`

## 3. Admin import

1. Adminga kiring: `/admin/`
2. `Cards` -> `Cards` bo'limiga o'ting
3. `Import Excel/CSV` tugmasini bosing
4. Fayl yuklang

Import vaqtida:
- `card_number`, `phone`, `expire`, `status`, `balance` normalizatsiya qilinadi
- noto'g'ri qatorlar reject qilinadi va warning sifatida ko'rsatiladi

## 4. Export command

```bash
python manage.py export_cards --output cards_export.csv
python manage.py export_cards --status active --output active_cards.csv
python manage.py export_cards --card-number "8600 1234 5678 9012" --output one_card.csv
python manage.py export_cards --phone "99 973 03 03" --output by_phone.csv
```

## 5. Fake messaging command (optional)

```bash
python manage.py send_fake_messages --status active
python manage.py send_fake_messages --phone "99 973 03 03" --chat-id 12345
python manage.py send_fake_messages --card-number "8600 1234 5678 9012" --lang UZ
```
