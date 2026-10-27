from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    firm: Mapped[str] = mapped_column(String(200), default="")
    project_name: Mapped[str] = mapped_column(String(200), default="")
    project_number: Mapped[str] = mapped_column(String(100), default="")
    building_name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[str] = mapped_column(String(60), default="")
    longitude: Mapped[str] = mapped_column(String(60), default="")
    year_built: Mapped[str] = mapped_column(String(30), default="")
    years_remodeled: Mapped[str] = mapped_column(String(100), default="")
    original_design_code: Mapped[str] = mapped_column(String(200), default="")
    area: Mapped[str] = mapped_column(String(60), default="")
    length: Mapped[str] = mapped_column(String(60), default="")
    width: Mapped[str] = mapped_column(String(60), default="")
    stories: Mapped[str] = mapped_column(String(40), default="")
    story_height: Mapped[str] = mapped_column(String(60), default="")
    total_height: Mapped[str] = mapped_column(String(60), default="")
    use: Mapped[str] = mapped_column(String(100), default="")
    gravity_system: Mapped[str] = mapped_column(Text, default="")
    transverse_walls: Mapped[str] = mapped_column(Text, default="")
    longitudinal_walls: Mapped[str] = mapped_column(Text, default="")
    roof_framing: Mapped[str] = mapped_column(Text, default="")
    floor_framing: Mapped[str] = mapped_column(Text, default="")
    ground_floor: Mapped[str] = mapped_column(Text, default="")
    columns: Mapped[str] = mapped_column(Text, default="")
    foundation: Mapped[str] = mapped_column(Text, default="")
    general_condition: Mapped[str] = mapped_column(Text, default="")
    levels_below_grade: Mapped[str] = mapped_column(String(40), default="")
    special_features: Mapped[str] = mapped_column(Text, default="")
    longitudinal_lateral_system: Mapped[str] = mapped_column(Text, default="")
    transverse_lateral_system: Mapped[str] = mapped_column(Text, default="")
    evaluation_data: Mapped[str] = mapped_column(Text, default="")
    seismicity: Mapped[str] = mapped_column(String(30), default="")
    performance_level: Mapped[str] = mapped_column(String(10), default="")
    building_type: Mapped[str] = mapped_column(String(30), default="")
    include_basic: Mapped[bool] = mapped_column(Boolean, default=True)
    include_structural: Mapped[bool] = mapped_column(Boolean, default=True)
    include_nonstructural: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_notes: Mapped[str] = mapped_column(Text, default="")

    checklists: Mapped[list["AssessmentChecklist"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    drawing_interpretations: Mapped[list["DrawingInterpretation"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="DrawingInterpretation.id"
    )
    calculations: Mapped[list["CalculationRecord"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="CalculationRecord.created_at"
    )
    photo_analyses: Mapped[list["PhotoAnalysis"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="PhotoAnalysis.id"
    )


class AssessmentChecklist(Base):
    __tablename__ = "assessment_checklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    form_id: Mapped[str] = mapped_column(String(100))
    source_pdf: Mapped[str] = mapped_column(Text, default="")
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text, default="")

    assessment: Mapped[Assessment] = relationship(back_populates="checklists")
    responses: Mapped[list["Response"]] = relationship(
        back_populates="assessment_checklist", cascade="all, delete-orphan"
    )


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_checklist_id: Mapped[int] = mapped_column(ForeignKey("assessment_checklists.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(10), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assessment_checklist: Mapped[AssessmentChecklist] = relationship(back_populates="responses")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(160), index=True)
    stored_name: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    caption: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    include_in_report: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessment: Mapped[Assessment] = relationship(back_populates="evidence")
    photo_analyses: Mapped[list["PhotoAnalysis"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan", order_by="PhotoAnalysis.id"
    )

    @property
    def is_image(self) -> bool:
        return (self.mime_type or "").startswith("image/")


class DrawingInterpretation(Base):
    """One run of reading uploaded plans and elevations into intake fields."""

    __tablename__ = "drawing_interpretations"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model: Mapped[str] = mapped_column(String(100), default="")
    evidence_ids: Mapped[str] = mapped_column(Text, default="[]")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    applied_fields: Mapped[str] = mapped_column(Text, default="[]")
    kept_fields: Mapped[str] = mapped_column(Text, default="[]")

    assessment: Mapped[Assessment] = relationship(back_populates="drawing_interpretations")

    @property
    def result(self) -> dict[str, Any]:
        return json.loads(self.result_json or "{}")

    @property
    def applied(self) -> list[str]:
        return json.loads(self.applied_fields or "[]")

    @property
    def kept(self) -> list[str]:
        return json.loads(self.kept_fields or "[]")


class CalculationRecord(Base):
    """An engineer-entered calculation supporting a checklist finding."""

    __tablename__ = "calculation_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(160), index=True)
    calculation_type: Mapped[str] = mapped_column(String(100))
    source_reference: Mapped[str] = mapped_column(Text, default="")
    inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    engineer_determination: Mapped[str] = mapped_column(String(10), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessment: Mapped[Assessment] = relationship(back_populates="calculations")

    @property
    def inputs(self) -> dict[str, Any]:
        return json.loads(self.inputs_json or "{}")

    @property
    def result(self) -> dict[str, Any]:
        return json.loads(self.result_json or "{}")


class PhotoAnalysis(Base):
    """One opt-in photo-analysis attempt, including failed and retried runs."""

    __tablename__ = "photo_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    model: Mapped[str] = mapped_column(String(100), default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="photo_analyses")
    evidence: Mapped[Evidence] = relationship(back_populates="photo_analyses")

    @property
    def context(self) -> dict[str, Any]:
        return json.loads(self.context_json or "{}")

    @property
    def result(self) -> dict[str, Any]:
        return json.loads(self.result_json or "{}")


def model_to_dict(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {field: getattr(obj, field) for field in fields}
