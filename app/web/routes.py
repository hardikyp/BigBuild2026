from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from sqlalchemy import select
from werkzeug.utils import secure_filename

from app.domain.models import Assessment, Evidence
from app.exports.json_export import assessment_json
from app.exports.pdf_export import make_pdf
from app.services.assessment import applicable_sections, get_catalog_form, response_for, summary, sync_checklists, update_assessment_from_form


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
            return redirect(url_for("main.intake", assessment_id=assessment.id))
    return render_template("intake.html", assessment=Assessment(), is_new=True, catalog=catalog())


@bp.route("/assessments/<int:assessment_id>/intake", methods=["GET", "POST"])
def intake(assessment_id: int):
    with db_session() as session:
        assessment = get_assessment(session, assessment_id)
        if assessment is None:
            return "Assessment not found", 404
        if request.method == "POST":
            update_assessment_from_form(assessment, request.form)
            if not assessment.performance_level or not assessment.building_type or not assessment.seismicity:
                flash("Choose performance objective, building type, and seismicity before beginning review.", "error")
            else:
                sync_checklists(session, assessment, catalog())
                assessment.status = "draft"
                session.commit()
                return redirect(url_for("main.review", assessment_id=assessment.id))
            session.commit()
        return render_template("intake.html", assessment=assessment, is_new=False, catalog=catalog())


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
            for item in section.items:
                response = response_for(session, checklist, item["item_id"])
                response.status = request.form.get(f"status_{item['item_id']}", "")
                response.comment = request.form.get(f"comment_{item['item_id']}", "").strip()
                response.reviewer_note = request.form.get(f"reviewer_{item['item_id']}", "").strip()
                upload = request.files.get(f"file_{item['item_id']}")
                if upload and upload.filename:
                    save_evidence_file(
                        session, assessment, item["item_id"], upload,
                        request.form.get(f"caption_{item['item_id']}", "").strip(),
                    )
            session.commit()
            if request.form.get("action") == "previous":
                form_index, section_index = previous_location(checklists, catalog(), assessment, form_index, section_index)
            elif request.form.get("action") == "summary":
                return redirect(url_for("main.summary_view", assessment_id=assessment.id))
            else:
                form_index, section_index = next_location(checklists, catalog(), assessment, form_index, section_index)
            return redirect(url_for("main.review_form", assessment_id=assessment.id, form_index=form_index, section_index=section_index))
        responses = {response.item_id: response for response in checklist.responses}
        progress = summary(catalog(), assessment)["counters"]
        return render_template(
            "review.html", assessment=assessment, form=form, checklist=checklist, section=section,
            form_index=form_index, section_index=section_index, form_count=len(checklists),
            section_count=len(sections), responses=responses, progress=progress,
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


def save_evidence_file(session, assessment, item_id: str, upload, caption: str) -> None:
    original_name = secure_filename(upload.filename) or "evidence"
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    upload_root = Path(current_app.config["UPLOAD_ROOT"]) / str(assessment.id)
    upload_root.mkdir(parents=True, exist_ok=True)
    path = upload_root / stored_name
    upload.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    session.add(Evidence(
        assessment=assessment,
        item_id=item_id,
        stored_name=stored_name,
        original_name=original_name,
        mime_type=upload.mimetype or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        caption=caption,
        sha256=digest,
    ))


@bp.get("/assessments/<int:assessment_id>/evidence/<path:stored_name>")
def download_evidence(assessment_id: int, stored_name: str):
    return send_from_directory(Path(current_app.config["UPLOAD_ROOT"]) / str(assessment_id), stored_name, as_attachment=False)


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
        payload = make_pdf(catalog(), assessment)
        from flask import Response
        return Response(payload, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename=assessment-{assessment.id}.pdf"})
