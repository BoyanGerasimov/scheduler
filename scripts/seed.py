import asyncio
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Doctor, DoctorWorkingHour, Patient, Role, User, Visit, VisitStatus
from app.security import hash_password


def next_weekday_at(days_ahead: int, hour: int, minute: int) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    while base.weekday() > 4:
        base += timedelta(days=1)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def clear_data(db: AsyncSession) -> None:
    await db.execute(delete(Visit))
    await db.execute(delete(Patient))
    await db.execute(delete(DoctorWorkingHour))
    await db.execute(delete(Doctor))
    await db.execute(delete(User))
    await db.commit()


async def seed_users(db: AsyncSession):
    doctor_user_1 = User(email='doctor1@example.com', password_hash=hash_password('password123'), role=Role.doctor)
    doctor_user_2 = User(email='doctor2@example.com', password_hash=hash_password('password123'), role=Role.doctor)
    patient_user_1 = User(email='patient1@example.com', password_hash=hash_password('password123'), role=Role.patient)
    patient_user_2 = User(email='patient2@example.com', password_hash=hash_password('password123'), role=Role.patient)
    patient_user_3 = User(email='patient3@example.com', password_hash=hash_password('password123'), role=Role.patient)

    db.add_all([doctor_user_1, doctor_user_2, patient_user_1, patient_user_2, patient_user_3])
    await db.flush()

    doctor_1 = Doctor(id=doctor_user_1.id, name='Dr. Ivan Petrov', email='doctor1@example.com', address='Sofia, Mladost 1')
    doctor_2 = Doctor(id=doctor_user_2.id, name='Dr. Maria Georgieva', email='doctor2@example.com', address='Plovdiv, Center')
    db.add_all([doctor_1, doctor_2])

    working_hours = []
    for weekday in range(5):
        working_hours.append(DoctorWorkingHour(doctor_id=doctor_1.id, weekday=weekday, start_time=time(8, 30), end_time=time(12, 0)))
        working_hours.append(DoctorWorkingHour(doctor_id=doctor_1.id, weekday=weekday, start_time=time(13, 0), end_time=time(18, 30)))
        working_hours.append(DoctorWorkingHour(doctor_id=doctor_2.id, weekday=weekday, start_time=time(9, 0), end_time=time(17, 0)))
    working_hours.append(DoctorWorkingHour(doctor_id=doctor_1.id, weekday=5, start_time=time(9, 0), end_time=time(12, 30)))
    db.add_all(working_hours)

    patient_1 = Patient(id=patient_user_1.id, name='Georgi Ivanov', email='patient1@example.com', phone='+359888111222', doctor_id=doctor_1.id)
    patient_2 = Patient(id=patient_user_2.id, name='Elena Stoyanova', email='patient2@example.com', phone='+359888333444', doctor_id=doctor_1.id)
    patient_3 = Patient(id=patient_user_3.id, name='Petar Dimitrov', email='patient3@example.com', phone='+359888555666', doctor_id=doctor_2.id)
    db.add_all([patient_1, patient_2, patient_3])

    visit_1_start = next_weekday_at(2, 10, 0)
    visit_2_start = next_weekday_at(3, 11, 0)
    visit_3_start = next_weekday_at(4, 14, 0)
    visits = [
        Visit(
            doctor_id=doctor_1.id,
            patient_id=patient_1.id,
            starts_at=visit_1_start,
            ends_at=visit_1_start + timedelta(minutes=30),
            status=VisitStatus.active,
        ),
        Visit(
            doctor_id=doctor_1.id,
            patient_id=patient_2.id,
            starts_at=visit_2_start,
            ends_at=visit_2_start + timedelta(minutes=30),
            status=VisitStatus.active,
        ),
        Visit(
            doctor_id=doctor_2.id,
            patient_id=patient_3.id,
            starts_at=visit_3_start,
            ends_at=visit_3_start + timedelta(minutes=20),
            status=VisitStatus.active,
        ),
    ]
    db.add_all(visits)
    await db.commit()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await clear_data(db)
        await seed_users(db)
    print('Dummy data inserted successfully.')


if __name__ == '__main__':
    asyncio.run(main())
