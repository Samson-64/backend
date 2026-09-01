from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.models.person import Person
from app.schemas.booking import PersonResponse

router = APIRouter(prefix="/api/people", tags=["people"])


@router.get("", response_model=list[PersonResponse])
def list_people(db: Session = Depends(get_db)):
    people = db.query(Person).all()
    return [PersonResponse.model_validate(p) for p in people]
