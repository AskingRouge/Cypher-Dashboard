from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.checks.scheduler import remove_service_job, schedule_service
from app.decorators import login_required, service_creator
from app.extensions import db
from app.forms import ServiceForm
from app.models import Incident, Service
from app.services import build_service_summaries

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
@login_required
def index():
    services = db.session.scalars(db.select(Service).order_by(Service.name)).all()
    summaries = build_service_summaries(services)
    return render_template("dashboard.html", summaries=summaries)


@dashboard_bp.route("/services/new", methods=["GET", "POST"])
@login_required
def create_service():
    form = ServiceForm()
    if form.validate_on_submit():
        data = form.normalized
        service = Service(
            name=data.name,
            target=data.target,
            check_type=data.check_type,
            interval_seconds=data.interval_seconds,
            expected_status_code=data.expected_status_code,
            creator=service_creator(),
        )
        try:
            db.session.add(service)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Could not create service")
            flash("The service could not be saved. Please try again.", "error")
        else:
            schedule_service(current_app._get_current_object(), service)
            flash(f"Added {service.name}.", "success")
            return redirect(url_for("dashboard.service_detail", service_id=service.id))
    return render_template("service_form.html", form=form, page_title="Add service")


@dashboard_bp.get("/services/<int:service_id>")
@login_required
def service_detail(service_id: int):
    service = db.get_or_404(Service, service_id)
    summary = build_service_summaries([service])[0]
    incidents = db.session.scalars(
        db.select(Incident)
        .where(Incident.service_id == service_id)
        .order_by(Incident.started_at.desc())
        .limit(100)
    ).all()
    return render_template(
        "service_detail.html",
        service=service,
        summary=summary,
        incidents=incidents,
    )


@dashboard_bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@login_required
def edit_service(service_id: int):
    service = db.get_or_404(Service, service_id)
    form = ServiceForm(obj=service)
    if form.validate_on_submit():
        data = form.normalized
        service.name = data.name
        service.target = data.target
        service.check_type = data.check_type
        service.interval_seconds = data.interval_seconds
        service.expected_status_code = data.expected_status_code
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Could not update service %s", service_id)
            flash("The service could not be updated. Please try again.", "error")
        else:
            schedule_service(current_app._get_current_object(), service)
            flash(f"Updated {service.name}.", "success")
            return redirect(url_for("dashboard.service_detail", service_id=service.id))
    return render_template(
        "service_form.html",
        form=form,
        page_title=f"Edit {service.name}",
        service=service,
    )


@dashboard_bp.post("/services/<int:service_id>/delete")
@login_required
def delete_service(service_id: int):
    service = db.get_or_404(Service, service_id)
    service_name = service.name
    try:
        db.session.delete(service)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not delete service %s", service_id)
        flash("The service could not be deleted. Please try again.", "error")
        return redirect(url_for("dashboard.service_detail", service_id=service_id))
    remove_service_job(service_id)
    flash(f"Deleted {service_name}.", "success")
    return redirect(url_for("dashboard.index"))
