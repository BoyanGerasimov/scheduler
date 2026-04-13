from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, engine, get_db
from app.models import Doctor, Patient, PermanentScheduleChange, Role, TemporaryScheduleChange, User, Visit, VisitStatus
from app.schemas import (
    LoginRequest,
    MessageResponse,
    PermanentChangeRequest,
    RegisterDoctorRequest,
    RegisterPatientRequest,
    TemporaryChangeRequest,
    TokenResponse,
    UpdateWorkingHoursRequest,
    VisitCreateRequest,
    VisitResponse,
)
from app.security import create_access_token, get_current_user, hash_password, verify_password
from app.services import ensure_patient_exists, replace_base_working_hours, schedule_to_dict, validate_visit_rules

@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title='Scheduler API', lifespan=lifespan)


@app.post('/auth/register/doctor', response_model=TokenResponse)
async def register_doctor(payload: RegisterDoctorRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email already registered')

    user = User(email=payload.email, password_hash=hash_password(payload.password), role=Role.doctor)
    db.add(user)
    await db.flush()

    doctor = Doctor(id=user.id, name=payload.name, email=payload.email, address=payload.address)
    db.add(doctor)
    await replace_base_working_hours(db, doctor.id, payload.weekly_schedule)

    await db.commit()
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@app.post('/auth/register/patient', response_model=TokenResponse)
async def register_patient(payload: RegisterPatientRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email already registered')

    doctor = await db.execute(select(Doctor).where(Doctor.id == payload.doctor_id))
    if doctor.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Doctor not found')

    user = User(email=payload.email, password_hash=hash_password(payload.password), role=Role.patient)
    db.add(user)
    await db.flush()

    patient = Patient(id=user.id, name=payload.name, email=payload.email, phone=payload.phone, doctor_id=payload.doctor_id)
    db.add(patient)

    await db.commit()
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@app.post('/auth/login', response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@app.put('/doctors/me/working-hours', response_model=MessageResponse)
async def update_working_hours(
    payload: UpdateWorkingHoursRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.doctor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only doctors can update working hours')

    await replace_base_working_hours(db, current_user.id, payload.weekly_schedule)
    await db.commit()
    return MessageResponse(message='Working hours updated')


@app.post('/doctors/me/temporary-working-hours', response_model=MessageResponse)
async def add_temporary_change(
    payload: TemporaryChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.doctor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only doctors can add temporary changes')

    existing = await db.execute(select(TemporaryScheduleChange).where(TemporaryScheduleChange.doctor_id == current_user.id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Temporary change already exists for this doctor')

    change = TemporaryScheduleChange(
        doctor_id=current_user.id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        schedule=schedule_to_dict(payload.weekly_schedule),
    )
    db.add(change)
    await db.commit()
    return MessageResponse(message='Temporary working hours change added')


@app.post('/doctors/me/permanent-working-hours', response_model=MessageResponse)
async def add_permanent_change(
    payload: PermanentChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.doctor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only doctors can add permanent changes')

    minimum_date = datetime.now(timezone.utc).date() + timedelta(days=7)
    if payload.effective_from < minimum_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Permanent changes must start at least one week in the future')

    change = PermanentScheduleChange(
        doctor_id=current_user.id,
        effective_from=payload.effective_from,
        schedule=schedule_to_dict(payload.weekly_schedule),
    )
    db.add(change)
    await db.commit()
    return MessageResponse(message='Permanent working hours change added')


@app.post('/patients/me/visits', response_model=VisitResponse)
async def create_visit(
    payload: VisitCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != Role.patient:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only patients can create visits')

    patient = await ensure_patient_exists(db, current_user.id)
    await validate_visit_rules(db, patient.doctor_id, patient.id, payload.starts_at, payload.ends_at)

    visit = Visit(
        doctor_id=patient.doctor_id,
        patient_id=patient.id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status=VisitStatus.active,
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return VisitResponse.model_validate(visit)


@app.post('/visits/{visit_id}/cancel', response_model=MessageResponse)
async def cancel_visit(
    visit_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Visit).where(Visit.id == visit_id))
    visit = result.scalar_one_or_none()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Visit not found')
    if visit.status == VisitStatus.cancelled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Visit already cancelled')

    if current_user.role == Role.doctor and visit.doctor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Forbidden')
    if current_user.role == Role.patient and visit.patient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Forbidden')

    now = datetime.now(timezone.utc)
    visit_start = visit.starts_at if visit.starts_at.tzinfo else visit.starts_at.replace(tzinfo=timezone.utc)
    if visit_start <= now + timedelta(hours=12):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Visit cannot be cancelled later than 12 hours before start')

    visit.status = VisitStatus.cancelled
    visit.cancelled_by = current_user.role.value
    await db.commit()

    return MessageResponse(message='Visit cancelled')


@app.get('/me/visits', response_model=list[VisitResponse])
async def my_visits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.doctor:
        result = await db.execute(select(Visit).where(Visit.doctor_id == current_user.id).order_by(Visit.starts_at.asc()))
    else:
        result = await db.execute(select(Visit).where(Visit.patient_id == current_user.id).order_by(Visit.starts_at.asc()))
    visits = list(result.scalars().all())
    return [VisitResponse.model_validate(v) for v in visits]
