from datetime import datetime, timedelta, timezone
from uuid import UUID
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Patient, Visit, VisitStatus
from tests.conftest import TestSessionLocal


def base_schedule():
    return [
        {'weekday': 0, 'intervals': [{'start': '08:30:00', 'end': '12:00:00'}, {'start': '13:00:00', 'end': '18:30:00'}]},
        {'weekday': 1, 'intervals': [{'start': '08:30:00', 'end': '18:30:00'}]},
        {'weekday': 2, 'intervals': [{'start': '08:30:00', 'end': '18:30:00'}]},
        {'weekday': 3, 'intervals': [{'start': '08:30:00', 'end': '18:30:00'}]},
        {'weekday': 4, 'intervals': [{'start': '08:30:00', 'end': '18:30:00'}]},
        {'weekday': 5, 'intervals': [{'start': '09:00:00', 'end': '12:30:00'}]},
        {'weekday': 6, 'intervals': []},
    ]


async def register_doctor(client):
    suffix = uuid4().hex[:8]
    email = f'doctor_{suffix}@example.com'
    payload = {
        'name': 'Doctor One',
        'email': email,
        'password': 'password123',
        'address': 'Sofia',
        'weekly_schedule': base_schedule(),
    }
    response = await client.post('/auth/register/doctor', json=payload)
    assert response.status_code == 200
    token = response.json()['access_token']
    return token, email


async def register_patient(client, doctor_token, doctor_email):
    doctor_visits = await client.get('/me/visits', headers={'Authorization': f'Bearer {doctor_token}'})
    assert doctor_visits.status_code == 200

    me = await client.post('/auth/login', json={'email': doctor_email, 'password': 'password123'})
    assert me.status_code == 200

    from app.security import jwt, settings

    doctor_id = jwt.decode(doctor_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])['sub']

    payload = {
        'name': 'Patient One',
        'email': f'patient_{uuid4().hex[:8]}@example.com',
        'password': 'password123',
        'phone': '+359888000111',
        'doctor_id': doctor_id,
    }
    response = await client.post('/auth/register/patient', json=payload)
    assert response.status_code == 200
    return response.json()['access_token']


def next_weekday_at(hour: int, minute: int):
    now = datetime.now(timezone.utc)
    target = now + timedelta(days=2)
    while target.weekday() > 4:
        target += timedelta(days=1)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def get_patient_id_from_token(token: str):
    from app.security import jwt, settings

    patient_id = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])['sub']
    return UUID(patient_id)


async def register_doctor_and_patient(client):
    doctor_token, doctor_email = await register_doctor(client)
    patient_token = await register_patient(client, doctor_token, doctor_email)
    return doctor_token, patient_token


@pytest.mark.asyncio
async def test_visit_creation_and_overlap(client):
    _, patient_token = await register_doctor_and_patient(client)

    starts_at = next_weekday_at(10, 0)
    ends_at = starts_at + timedelta(minutes=30)

    create_first = await client.post(
        '/patients/me/visits',
        json={'starts_at': starts_at.isoformat(), 'ends_at': ends_at.isoformat()},
        headers={'Authorization': f'Bearer {patient_token}'},
    )
    assert create_first.status_code == 200

    create_overlap = await client.post(
        '/patients/me/visits',
        json={'starts_at': starts_at.isoformat(), 'ends_at': (ends_at + timedelta(minutes=10)).isoformat()},
        headers={'Authorization': f'Bearer {patient_token}'},
    )
    assert create_overlap.status_code == 400
    assert create_overlap.json()['detail'] == 'Visit overlaps with another visit'


@pytest.mark.asyncio
async def test_cancel_visit_success(client):
    _, patient_token = await register_doctor_and_patient(client)

    starts_at = next_weekday_at(11, 0)
    ends_at = starts_at + timedelta(minutes=20)

    create = await client.post(
        '/patients/me/visits',
        json={'starts_at': (starts_at + timedelta(days=2)).isoformat(), 'ends_at': (ends_at + timedelta(days=2)).isoformat()},
        headers={'Authorization': f'Bearer {patient_token}'},
    )
    assert create.status_code == 200
    visit_id = create.json()['id']

    cancel = await client.post(f'/visits/{visit_id}/cancel', headers={'Authorization': f'Bearer {patient_token}'})
    assert cancel.status_code == 200


@pytest.mark.asyncio
async def test_create_visit_requires_auth(client):
    starts_at = next_weekday_at(10, 0) + timedelta(days=3)
    ends_at = starts_at + timedelta(minutes=30)
    response = await client.post('/patients/me/visits', json={'starts_at': starts_at.isoformat(), 'ends_at': ends_at.isoformat()})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_visit_less_than_24_hours_fails(client):
    _, patient_token = await register_doctor_and_patient(client)

    starts_at = datetime.now(timezone.utc) + timedelta(hours=23)
    ends_at = starts_at + timedelta(minutes=20)
    response = await client.post(
        '/patients/me/visits',
        json={'starts_at': starts_at.isoformat(), 'ends_at': ends_at.isoformat()},
        headers={'Authorization': f'Bearer {patient_token}'},
    )
    assert response.status_code == 400
    assert response.json()['detail'] == 'Visit must be created at least 24 hours in advance'


@pytest.mark.asyncio
async def test_create_visit_outside_working_hours_fails(client):
    _, patient_token = await register_doctor_and_patient(client)

    starts_at = next_weekday_at(7, 0) + timedelta(days=3)
    ends_at = starts_at + timedelta(minutes=20)
    response = await client.post(
        '/patients/me/visits',
        json={'starts_at': starts_at.isoformat(), 'ends_at': ends_at.isoformat()},
        headers={'Authorization': f'Bearer {patient_token}'},
    )
    assert response.status_code == 400
    assert response.json()['detail'] == 'Visit must be inside doctor working hours'


@pytest.mark.asyncio
async def test_single_temporary_change_per_doctor(client):
    doctor_token, _ = await register_doctor(client)

    starts_at = datetime.now(timezone.utc) + timedelta(days=2)
    ends_at = starts_at + timedelta(days=2)
    payload = {
        'starts_at': starts_at.isoformat(),
        'ends_at': ends_at.isoformat(),
        'weekly_schedule': base_schedule(),
    }
    first = await client.post('/doctors/me/temporary-working-hours', json=payload, headers={'Authorization': f'Bearer {doctor_token}'})
    assert first.status_code == 200
    second = await client.post('/doctors/me/temporary-working-hours', json=payload, headers={'Authorization': f'Bearer {doctor_token}'})
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_permanent_change_must_be_one_week_in_future(client):
    doctor_token, _ = await register_doctor(client)
    payload = {
        'effective_from': (datetime.now(timezone.utc).date() + timedelta(days=3)).isoformat(),
        'weekly_schedule': base_schedule(),
    }
    response = await client.post('/doctors/me/permanent-working-hours', json=payload, headers={'Authorization': f'Bearer {doctor_token}'})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cancel_later_than_12_hours_fails(client):
    _, patient_token = await register_doctor_and_patient(client)
    patient_id = await get_patient_id_from_token(patient_token)

    async with TestSessionLocal() as db:
        result = await db.execute(select(Patient).where(Patient.id == patient_id))
        patient = result.scalar_one()
        visit = Visit(
            doctor_id=patient.doctor_id,
            patient_id=patient.id,
            starts_at=datetime.now(timezone.utc) + timedelta(hours=11),
            ends_at=datetime.now(timezone.utc) + timedelta(hours=11, minutes=20),
            status=VisitStatus.active,
        )
        db.add(visit)
        await db.commit()
        await db.refresh(visit)
        visit_id = visit.id

    response = await client.post(f'/visits/{visit_id}/cancel', headers={'Authorization': f'Bearer {patient_token}'})
    assert response.status_code == 400
    assert response.json()['detail'] == 'Visit cannot be cancelled later than 12 hours before start'
