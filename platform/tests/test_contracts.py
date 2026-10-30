import json

from app.export_contracts import export


def test_export_agrees_with_run_dtos_and_documents_actual_error_status(tmp_path):
    export(tmp_path)
    schema = json.loads((tmp_path / "platform-openapi.json").read_text())
    models = schema["components"]["schemas"]
    assert models["RunDto"]["properties"]["projectId"]["format"] == "uuid"
    assert "requirementsSnapshot" not in models["RunDto"]["properties"]
    assert models["RunDetailsDto"]["properties"]["steps"]["type"] == "array"
    operation = schema["paths"]["/api/v1/projects/{project_id}/runs"]["post"]
    assert "202" in operation["responses"] and "400" in operation["responses"]
    assert "422" not in operation["responses"]
    ts = (tmp_path / "runs.ts").read_text()
    assert "export interface RunDetailsDto extends RunDto" in ts
    assert "projectId: string;" in ts and "currentStep: string | null;" in ts
