from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models import CheckType
from app.validation import ServiceInput, normalize_service_input


class ServiceForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[DataRequired(), Length(max=100)],
        render_kw={"placeholder": "Home Assistant"},
    )
    target = StringField(
        "Target",
        validators=[DataRequired(), Length(max=2048)],
        render_kw={"placeholder": "https://home.example.test"},
    )
    check_type = SelectField(
        "Check type",
        choices=[
            (CheckType.HTTP.value, "HTTP"),
            (CheckType.PING.value, "Ping"),
            (CheckType.TCP_PORT.value, "TCP port"),
        ],
        coerce=CheckType,
        default=CheckType.HTTP,
        validators=[DataRequired()],
    )
    interval_seconds = IntegerField(
        "Check interval (seconds)",
        validators=[DataRequired(), NumberRange(min=10, max=86_400)],
        default=60,
    )
    expected_status_code = IntegerField(
        "Expected HTTP status",
        validators=[Optional(), NumberRange(min=100, max=599)],
        default=200,
    )
    submit = SubmitField("Save service")

    _normalized: ServiceInput | None = None

    def validate(self, extra_validators=None) -> bool:
        if not super().validate(extra_validators):
            return False

        normalized, errors = normalize_service_input(
            {
                "name": self.name.data,
                "target": self.target.data,
                "check_type": self.check_type.data,
                "interval_seconds": self.interval_seconds.data,
                "expected_status_code": self.expected_status_code.data,
            }
        )
        for field_name, messages in errors.items():
            field = getattr(self, field_name)
            field.errors = [*field.errors, *messages]
        self._normalized = normalized
        return normalized is not None

    @property
    def normalized(self) -> ServiceInput:
        if self._normalized is None:
            raise RuntimeError("Read normalized data only after successful validation.")
        return self._normalized
