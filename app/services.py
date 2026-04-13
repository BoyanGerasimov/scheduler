from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Doctor,
    DoctorWorkingHour,
    Patient,
    PermanentScheduleChange,
    Role,
    TemporaryScheduleChange,
    User,
    Visit,
    VisitStatus,
)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def schedule_to_dict(weekly_schedule) -> dict:
    result: dict[str, list[dict[str, str]]] = {}
    for day in weekly_schedule:
        result[str(day.weekday)] = [
            {'start': interval.start.isoformat(), 'end': interval.end.isoformat()} for interval in day.intervals
        ]
    return result


def dict_to_intervals(schedule: dict, weekday: int) -> list[tuple[time, time]]:
    raw = schedule.get(str(weekday), [])
    return [(time.fromisoformat(item['start']), time.fromisoformat(item['end'])) for item in raw]


async def ensure_doctor_exists(db: AsyncSession, doctor_id):
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Doctor not found')
    return doctor


async def ensure_patient_exists(db: AsyncSession, patient_id):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Patient not found')
    return patient


async def replace_base_working_hours(db: AsyncSession, doctor_id, weekly_schedule) -> None:
    await db.execute(delete(DoctorWorkingHour).where(DoctorWorkingHour.doctor_id == doctor_id))
    for day in weekly_schedule:
        for interval in day.intervals:
            db.add(
                DoctorWorkingHour(
                    doctor_id=doctor_id,
                    weekday=day.weekday,
                    start_time=interval.start,
                    end_time=interval.end,
                )
            )


async def get_effective_schedule(db: AsyncSession, doctor_id, at_dt: datetime) -> dict:
    at_dt = ensure_utc(at_dt)

    temp_result = await db.execute(select(TemporaryScheduleChange).where(TemporaryScheduleChange.doctor_id == doctor_id))
    temp_change = temp_result.scalar_one_or_none()
    if temp_change:
        if ensure_utc(temp_change.starts_at) <= at_dt and ensure_utc(temp_change.ends_at) >= at_dt:
            return temp_change.schedule

    perm_result = await db.execute(
        select(PermanentScheduleChange)
        .where(and_(PermanentScheduleChange.doctor_id == doctor_id, PermanentScheduleChange.effective_from <= at_dt.date()))
        .order_by(PermanentScheduleChange.effective_from.desc())
    )
    perm_change = perm_result.scalars().first()
    if perm_change:
        return perm_change.schedule

    base_result = await db.execute(select(DoctorWorkingHour).where(DoctorWorkingHour.doctor_id == doctor_id))
    segments = base_result.scalars().all()
    schedule: dict[str, list[dict[str, str]]] = {}
    for seg in segments:
        key = str(seg.weekday)
        schedule.setdefault(key, []).append({'start': seg.start_time.isoformat(), 'end': seg.end_time.isoformat()})
    return schedule


def is_within_intervals(start: datetime, end: datetime, intervals: list[tuple[time, time]]) -> bool:
    if start.date() != end.date():
        return False
    start_time = start.timetz().replace(tzinfo=None)
    end_time = end.timetz().replace(tzinfo=None)
    for int_start, int_end in intervals:
        if start_time >= int_start and end_time <= int_end:
            return True
    return False


async def validate_visit_rules(db: AsyncSession, doctor_id, patient_id, starts_at: datetime, ends_at: datetime) -> None:
    starts_at = ensure_utc(starts_at)
    ends_at = ensure_utc(ends_at)
    now = datetime.now(timezone.utc)

    if starts_at <= now + timedelta(hours=24):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Visit must be created at least 24 hours in advance')

    patient = await ensure_patient_exists(db, patient_id)
    if patient.doctor_id != doctor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Doctor must be personal doctor of patient')

    schedule = await get_effective_schedule(db, doctor_id, starts_at)
    weekday = starts_at.weekday()
    intervals = dict_to_intervals(schedule, weekday)
    if not is_within_intervals(starts_at, ends_at, intervals):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Visit must be inside doctor working hours')

    overlap_result = await db.execute(
        select(Visit).where(
            and_(
                Visit.doctor_id == doctor_id,
                Visit.status == VisitStatus.active,
                or_(
                    and_(Visit.starts_at < ends_at, Visit.ends_at > starts_at),
                ),
            )
        )
    )
    overlap = overlap_result.scalar_one_or_none()
    if overlap is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Visit overlaps with another visit')


async def get_user_visits(db: AsyncSession, user: User) -> list[Visit]:
    if user.role == Role.doctor:
        result = await db.execute(select(Visit).where(Visit.doctor_id == user.id).order_by(Visit.starts_at.asc()))
    else:
        result = await db.execute(select(Visit).where(Visit.patient_id == user.id).order_by(Visit.starts_at.asc()))
    return list(result.scalars().all())
