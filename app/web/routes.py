from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from sqlalchemy import select
from werkzeug.security import safe_join
from werkzeug.utils import secure_filename

from app.domain.models import Assessment, DrawingInterpretation, Evidence
from app.exports.json_export import assessment_json
from app.exports.pdf_export import make_pdf
from app.services.assessment import FIELD_LABELS, applicable_sections, get_catalog_form, response_for, summary, sync_checklists, update_assessment_from_form
from app.services.drawings import DRAWING_ROLES, DrawingError, apply_interpretation, claude_interpreter, interpretation_record, read_drawing
from app.services.photos import PHOTO_ACCEPT, photo_mime_type, thumbnail_path


bp = Blueprint("main", __name__)


def db_session():
    return current_app.extensions["morgan_session"]()


def catalog():
    return current_app.extensions["morgan_catalog"]


def get_assessment(session, assessment_id: int) -> Assessment | None:
    return session.get(Assessment, assessment_id)


def status_label(status: str) -> str:
    return {"C": "Compliant", "NC": "Noncompliant", "N/A": "Not applicable", "U": "Unknown", "incomplete": "Incomplete"}.get(status, "Not reviewed")


@bp.app_context_processor
def inject_helpers():
    return {"status_label": status_label, "level_label": {"very_low": "Very Low", "low": "Low", "moderate": "Moderate", "high": "High"}.get, "getattr": getattr}


@bp.app_errorhandler(413)
def upload_too_large(error):
    flash("Upload too large. Nothing in that save was stored; try fewer photos at a time.", "error")
    return redirect(request.referrer or url_for("main.assessments"))


@bp.get("/")
def home():
    return redirect(url_for("main.assessments"))


@bp.get("/assessments")
def assessments():
    with db_session() as session:
        records = session.scalars(select(Assessment).order_by(Assessment.updated_at.desc())).all()
        return render_template("assessments.html", assessments=records)


@bp.route("/assessments/new", methods=["GET", "POST"])
def new_assessment():
    if request.method == "POST":
        with db_session() as session:
            assessment = Assessment()
            update_assessment_from_form(assessment, request.form)
            session.add(assessment)
            session.commit()
            if request.form.get("action") == "interpret":
                interpret_drawings(session, assessment)
                session.commit()
            return redirect(url_for("main.intake", assessment_id=assessment.id))
    return render_template(
        "intake.html", assessment=Assessment(), is_new=True, catalog=catalog(),
        interpretation=None, drawing_fields={}, field_labels=FIELD_LABELS,
    )


@bp.route("/assessments/<int:assessment_id>/intake", methods=["GET", "POST"])
def intake(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        if request.method == "POST":
            update_assessment_from_form(assessment, request.form)
            if request.form.get("action") == "interpret":
                interpret_drawings(session, assessment)
                session.commit()
                return redirect(url_for("main.intake", assessment_id=assessment.id))
            if not assessment.performance_level or not assessment.building_type or not assessment.seismicity:
                flash("Choose performance objective, building type, and seismicity before beginning review.", "error")
            else:
                sync_checklists(session, assessment, catalog())
                assessment.status = "draft"
                session.commit()
                return redirect(url_for("main.review", assessment_id=assessment.id))
            session.commit()
        latest = assessment.drawing_interpretations[-1] if assessment.drawing_interpretations else None
        return render_template(
            "intake.html", assessment=assessment, is_new=False, catalog=catalog(),
            interpretation=latest, drawing_fields=drawing_field_map(latest), field_labels=FIELD_LABELS,
        )


def drawing_field_map(interpretation: DrawingInterpretation | None) -> dict[str, dict]:
    """Interpreted values keyed by field, marked with whether each was applied to the form."""
    if interpretation is None:
        return {}
    applied = set(interpretation.applied)
    return {entry["field"]: {**entry, "applied": entry["field"] in applied} for entry in interpretation.result.get("fields", [])}


def interpret_drawings(session, assessment: Assessment) -> None:
    """Read the uploaded plan and elevation drawings and fill intake fields from them.

    Drawings are kept as evidence so the interpretation stays traceable to its sources.
    """
    uploads = [
        (role, upload)
        for role in DRAWING_ROLES
        for upload in request.files.getlist(f"drawing_{role}")
        if upload and upload.filename
    ]
    if not uploads:
        flash("Choose at least one plan or elevation drawing to interpret.", "error")
        return
    try:
        drawings = [read_drawing(role, upload.filename, upload.read()) for role, upload in uploads]
        interpreter = current_app.config.get("DRAWING_INTERPRETER") or claude_interpreter
        interpretation = interpreter(drawings)
    except DrawingError as error:
        flash(str(error), "error")
        return
    evidence_ids = []
    for (role, upload), drawing in zip(uploads, drawings):
        upload.stream.seek(0)
        evidence = save_evidence_file(
            session, assessment, f"drawings:{role}", upload, f"{DRAWING_ROLES[role]} used for intake interpretation",
            mime_type=drawing.mime_type, include_in_report=False,
        )
        session.flush()
        evidence_ids.append(evidence.id)
    result = apply_interpretation(assessment, interpretation, overwrite=request.form.get("overwrite_fields") == "on")
    session.add(DrawingInterpretation(assessment=assessment, **interpretation_record(interpretation, result, evidence_ids)))
    if not interpretation.fields:
        flash("No intake fields could be read from these drawings. Check that the sheets are legible.", "error")
        return
    message = f"Filled {len(result.applied)} field(s) from the drawings. Review each value before beginning the checklist."
    if result.kept:
        message += f" Kept your existing value for {len(result.kept)} field(s); the drawing values are listed below."
    flash(message, "success")


@bp.get("/assessments/<int:assessment_id>/review")
def review(assessment_id: int):
    return redirect(url_for("main.review_form", assessment_id=assessment_id, form_index=0, section_index=0))


@bp.route("/assessments/<int:assessment_id>/review/<int:form_index>/<int:section_index>", methods=["GET", "POST"])
def review_form(assessment_id: int, form_index: int, section_index: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        if not assessment.checklists:
            sync_checklists(session, assessment, catalog())
        checklists = list(assessment.checklists)
        if form_index < 0 or form_index >= len(checklists):
            return redirect(url_for("main.summary_view", assessment_id=assessment.id))
        checklist = checklists[form_index]
        form = get_catalog_form(catalog(), checklist.form_id)
        sections = applicable_sections(form, assessment.seismicity)
        if not sections:
            return redirect(url_for("main.summary_view", assessment_id=assessment.id))
        section_index = max(0, min(section_index, len(sections) - 1))
        section = SimpleNamespace(**sections[section_index])
        if request.method == "POST":
            rejected = []
            for item in section.items:
                item_id = item["item_id"]
                response = response_for(session, checklist, item_id)
                response.status = request.form.get(f"status_{item_id}", "")
                response.comment = request.form.get(f"comment_{item_id}", "").strip()
                response.reviewer_note = request.form.get(f"reviewer_{item_id}", "").strip()
                caption = request.form.get(f"caption_{item_id}", "").strip()
                include = request.form.get(f"include_{item_id}") == "on"
                for photo in request.files.getlist(f"photo_{item_id}"):
                    if photo and photo.filename and not save_photo(session, assessment, item_id, photo, caption, include):
                        rejected.append(photo.filename)
                upload = request.files.get(f"file_{item_id}")
                if upload and upload.filename:
                    save_evidence_file(session, assessment, item_id, upload, caption, include_in_report=include)
            shown = {int(value) for value in request.form.getlist("evidence_on_page") if value.isdigit()}
            for evidence in assessment.evidence:
                if evidence.id in shown:
                    evidence.include_in_report = request.form.get(f"report_{evidence.id}") == "on"
            session.commit()
            if rejected:
                flash(f"Not saved, not a JPEG, PNG, WebP or GIF photo: {', '.join(rejected)}", "error")
            if request.form.get("action") == "previous":
                form_index, section_index = previous_location(checklists, catalog(), assessment, form_index, section_index)
            elif request.form.get("action") == "summary":
                return redirect(url_for("main.summary_view", assessment_id=assessment.id))
            else:
                form_index, section_index = next_location(checklists, catalog(), assessment, form_index, section_index)
            return redirect(url_for("main.review_form", assessment_id=assessment.id, form_index=form_index, section_index=section_index))
        responses = {response.item_id: response for response in checklist.responses}
        evidence_by_item: dict[str, list[Evidence]] = {}
        for evidence in assessment.evidence:
            evidence_by_item.setdefault(evidence.item_id, []).append(evidence)
        progress = summary(catalog(), assessment)["counters"]
        sequence = locations(checklists, catalog(), assessment)
        return render_template(
            "review.html", assessment=assessment, form=form, checklist=checklist, section=section,
            form_index=form_index, section_index=section_index, form_count=len(checklists),
            section_count=len(sections), responses=responses, progress=progress,
            evidence_by_item=evidence_by_item, photo_accept=PHOTO_ACCEPT,
            is_last_page=bool(sequence) and (form_index, section_index) == sequence[-1],
        )


def locations(checklists, source_catalog, assessment):
    result = []
    for form_index, checklist in enumerate(checklists):
        form = get_catalog_form(source_catalog, checklist.form_id)
        for section_index, section in enumerate(applicable_sections(form, assessment.seismicity)):
            result.append((form_index, section_index))
    return result


def next_location(checklists, source_catalog, assessment, form_index, section_index):
    sequence = locations(checklists, source_catalog, assessment)
    current = sequence.index((form_index, section_index)) if (form_index, section_index) in sequence else -1
    return sequence[min(current + 1, len(sequence) - 1)]


def previous_location(checklists, source_catalog, assessment, form_index, section_index):
    sequence = locations(checklists, source_catalog, assessment)
    current = sequence.index((form_index, section_index)) if (form_index, section_index) in sequence else 0
    return sequence[max(current - 1, 0)]


@bp.get("/assessments/<int:assessment_id>/summary")
def summary_view(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        data = summary(catalog(), assessment)
        return render_template("summary.html", assessment=assessment, data=data)


@bp.post("/assessments/<int:assessment_id>/notes")
def save_notes(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        assessment.reviewer_notes = request.form.get("reviewer_notes", "").strip()
        session.commit()
    return redirect(url_for("main.summary_view", assessment_id=assessment_id))


@bp.post("/assessments/<int:assessment_id>/evidence")
def upload_evidence(assessment_id: int):
    upload = request.files.get("file")
    item_id = request.form.get("item_id", "")
    if not upload or not upload.filename or not item_id:
        flash("Choose a file and item before uploading evidence.", "error")
        return redirect(request.referrer or url_for("main.summary_view", assessment_id=assessment_id))
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        save_evidence_file(session, assessment, item_id, upload, request.form.get("caption", "").strip())
        session.commit()
    flash("Evidence uploaded.", "success")
    return redirect(request.referrer or url_for("main.summary_view", assessment_id=assessment_id))


def save_photo(session, assessment, item_id: str, photo, caption: str, include_in_report: bool) -> bool:
    mime_type = photo_mime_type(photo.read())
    if mime_type is None:
        return False
    photo.stream.seek(0)
    save_evidence_file(session, assessment, item_id, photo, caption, mime_type=mime_type, include_in_report=include_in_report)
    return True


def save_evidence_file(session, assessment, item_id: str, upload, caption: str, *, mime_type: str | None = None, include_in_report: bool = True) -> Evidence:
    original_name = secure_filename(upload.filename) or "evidence"
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    upload_root = Path(current_app.config["UPLOAD_ROOT"]) / str(assessment.id)
    upload_root.mkdir(parents=True, exist_ok=True)
    path = upload_root / stored_name
    upload.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = Evidence(
        assessment=assessment,
        item_id=item_id,
        stored_name=stored_name,
        original_name=original_name,
        mime_type=mime_type or upload.mimetype or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        caption=caption,
        sha256=digest,
        include_in_report=include_in_report,
    )
    session.add(evidence)
    return evidence


@bp.get("/assessments/<int:assessment_id>/evidence/<path:stored_name>")
def download_evidence(assessment_id: int, stored_name: str):
    return send_from_directory(Path(current_app.config["UPLOAD_ROOT"]) / str(assessment_id), stored_name, as_attachment=False)


@bp.get("/assessments/<int:assessment_id>/evidence-thumb/<path:stored_name>")
def evidence_thumbnail(assessment_id: int, stored_name: str):
    folder = Path(current_app.config["UPLOAD_ROOT"]) / str(assessment_id)
    original = safe_join(str(folder), stored_name)
    if original is None or not Path(original).is_file():
        abort(404)
    try:
        thumb = thumbnail_path(Path(original))
    except OSError:
        abort(404)
    return send_from_directory(thumb.parent, thumb.name, as_attachment=False)


@bp.post("/assessments/<int:assessment_id>/evidence/<int:evidence_id>/delete")
def delete_evidence(assessment_id: int, evidence_id: int):
    with db_session() as session:
        evidence = session.get(Evidence, evidence_id)
        # Drawings are referenced by intake interpretations, so they are not deleted from here.
        if evidence is None or evidence.assessment_id != assessment_id or evidence.item_id.startswith("drawings:"):
            abort(404)
        remove_evidence_files(evidence)
        session.delete(evidence)
        session.commit()
    if request.headers.get("HX-Request"):
        return ""
    flash("Photo deleted.", "success")
    return redirect(request.referrer or url_for("main.review", assessment_id=assessment_id))


@bp.post("/assessments/<int:assessment_id>/delete")
def delete_assessment(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            abort(404)
        name = assessment.project_name or "Untitled project"
        session.delete(assessment)
        session.commit()
    shutil.rmtree(Path(current_app.config["UPLOAD_ROOT"]) / str(assessment_id), ignore_errors=True)
    flash(f"Deleted assessment #{assessment_id} ({name}).", "success")
    return redirect(url_for("main.assessments"))


def remove_evidence_files(evidence: Evidence) -> None:
    folder = Path(current_app.config["UPLOAD_ROOT"]) / str(evidence.assessment_id)
    original = folder / evidence.stored_name
    (folder / "thumbs" / f"{original.stem}.jpg").unlink(missing_ok=True)
    original.unlink(missing_ok=True)


@bp.get("/assessments/<int:assessment_id>/export.json")
def export_json(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        payload = assessment_json(catalog(), assessment)
        response = jsonify(payload)
        response.headers["Content-Disposition"] = f"attachment; filename=assessment-{assessment.id}.json"
        return response


@bp.get("/assessments/<int:assessment_id>/export.pdf")
def export_pdf(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        payload = make_pdf(catalog(), assessment, Path(current_app.config["UPLOAD_ROOT"]))
        return send_file(
            BytesIO(payload),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"assessment-{assessment.id}.pdf",
        )
