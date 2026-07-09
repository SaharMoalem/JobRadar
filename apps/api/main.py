from __future__ import annotations

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.ports.compliance_check_port import ComplianceCheckPort
from src.adapters.compliance.http_robots_compliance_adapter import HttpRobotsComplianceAdapter
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.source_policy import SourcePolicyConfig, SourceValidationError

ERROR_STATUS_BY_CODE: dict[str, int] = {
    "SOURCE_NAME_INVALID": 400,
    "SOURCE_URL_INVALID": 400,
    "SOURCE_NOT_FOUND": 404,
    "SOURCE_NOT_ENABLED": 409,
    "SOURCE_COMPLIANCE_NOT_APPROVED": 409,
    "SOURCE_COMPLIANCE_CHECK_FAILED": 409,
    "SOURCE_ENABLED_LIMIT_EXCEEDED": 409,
}


class SourceCreateRequest(BaseModel):
    name: str
    base_url: str


class ComplianceRejectRequest(BaseModel):
    reason: str = "manual_rejection"


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    status: str
    compliance_status: str
    compliance_reason: str | None = None
    robots_check_passed: bool | None = None


def envelope(*, data=None, error=None, meta=None):
    return {"data": data, "error": error, "meta": meta or {}}


def error_response(exc: SourceValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


def create_app(
    *,
    max_enabled_sources: int = 50,
    compliance_checker: ComplianceCheckPort | None = None,
) -> FastAPI:
    app = FastAPI(title="JobRadar API")
    repository = InMemoryCareerSourceAdapter()
    service = CareerSourceService(
        repository=repository,
        config=SourcePolicyConfig(max_enabled_sources=max_enabled_sources),
    )
    compliance_service = SourceComplianceService(
        repository=repository,
        compliance_checker=compliance_checker or HttpRobotsComplianceAdapter(),
    )

    @app.post("/career-sources")
    def create_source(payload: SourceCreateRequest):
        try:
            source = service.create(payload.name, payload.base_url)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.get("/career-sources")
    def list_sources():
        items = [SourceResponse.model_validate(item).model_dump() for item in service.list_all()]
        return envelope(data=items)

    @app.patch("/career-sources/{source_id}")
    def update_source(source_id: str, payload: SourceCreateRequest):
        try:
            source = service.update(source_id, payload.name, payload.base_url)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/enable")
    def enable_source(source_id: str):
        try:
            source = service.enable(source_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/disable")
    def disable_source(source_id: str):
        try:
            source = service.disable(source_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/compliance/approve")
    def approve_compliance(source_id: str):
        try:
            source = compliance_service.approve(source_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/compliance/reject")
    def reject_compliance(source_id: str, payload: ComplianceRejectRequest):
        try:
            source = compliance_service.reject(source_id, reason=payload.reason)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/execute")
    def execute_source(source_id: str, x_correlation_id: str = Header(default="local")):
        try:
            source = compliance_service.attempt_execution(source_id, correlation_id=x_correlation_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(
            data=SourceResponse.model_validate(source).model_dump(),
            meta={"correlation_id": x_correlation_id, "execution": "accepted"},
        )

    return app


app = create_app()
