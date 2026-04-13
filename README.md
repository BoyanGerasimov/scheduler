# Scheduler API

Backend система за записване на посещения при лични лекари с FastAPI и PostgreSQL (Supabase).

## Технологии

- Python
- FastAPI
- SQLAlchemy
- Supabase PostgreSQL
- JWT авторизация
- Pytest

## Инсталация

1. Създай виртуална среда:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Инсталирай зависимости:

```bash
pip install -r requirements.txt
```

3. Създай `.env` файл:

```env
user=postgres.<project-ref>
password=<database-password>
host=aws-1-<region>.pooler.supabase.com
port=5432
dbname=postgres
JWT_SECRET=<your-secret>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_MINUTES=120
```

## Стартиране

```bash
uvicorn app.main:app --reload
```

API документация:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Основни правила

- Посещение може да се създаде само при личния лекар на пациента.
- Посещение трябва да е изцяло в работното време на лекаря.
- Посещение трябва да е създадено поне 24 часа предварително.
- Посещение не може да се застъпва с друго активно посещение при същия лекар.
- Отмяна е позволена само до 12 часа преди началото.
- За лекар е разрешена само една временна промяна в работното време.
- Постоянна промяна в работното време влиза в сила най-рано след 7 дни.

## Endpoint-и

### Публични

- `POST /auth/register/doctor`
- `POST /auth/register/patient`
- `POST /auth/login`

### Изискват Bearer token

- `PUT /doctors/me/working-hours`
- `POST /doctors/me/temporary-working-hours`
- `POST /doctors/me/permanent-working-hours`
- `POST /patients/me/visits`
- `POST /visits/{visit_id}/cancel`
- `GET /me/visits`

## Dummy данни

```bash
python scripts/seed.py
```

Seed скриптът създава примерни лекари, пациенти, графици и посещения.

## Тестване

```bash
python3 -m pytest -q
```

Тестовете покриват:

- успешен flow за регистрация, записване и отказ на посещение
- отказ при липса на оторизация
- отказ при създаване под 24 часа преди началото
- отказ при час извън работното време
- отказ при застъпване на посещения
- ограничение за една временна промяна
- ограничение за постоянна промяна под 7 дни
- отказ за отмяна под 12 часа до началото

