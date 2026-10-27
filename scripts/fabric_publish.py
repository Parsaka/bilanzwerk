"""Publish the Fabric items of this repository to one stage (dev or prod).

  uv run --extra deploy python scripts/fabric_publish.py --stage dev --workspace-id <id>

What it does, in order:
1. Copies the items (fabric/*.Notebook, fabric/*.DataPipeline, powerbi/*.SemanticModel,
   powerbi/*.Report) into a staging folder and replaces the stage placeholders:
   #{KEY_VAULT_URI}#, #{ALERT_EMAIL}#, #{STAGE}#, #{SQL_ENDPOINT}#, #{WAREHOUSE}#.
2. Uploads the project wheel and the zipped dbt project to the lakehouse (Files/wheels,
   Files/dbt), where the notebooks install and run them.
3. Publishes the items with fabric-cicd, which rewrites the logical IDs between items (pipeline
   -> notebook, report -> semantic model) to the IDs in the target workspace.

Both stages get the same Git content; only the values above differ (ADR-009, amendment). Auth:
Azure CLI login (locally) or the OIDC login of the GitHub workflow (azure/login).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.fabric.microsoft.com/v1"
ITEM_TYPES = ["Notebook", "DataPipeline", "SemanticModel", "Report"]
TEXT_SUFFIXES = {".json", ".py", ".tmdl", ".pbir", ".pbism", ".platform"}


def fabric_get(path: str, token: str) -> dict:
    import requests

    resp = requests.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def item_by_name(workspace_id: str, kind: str, name: str, token: str) -> dict:
    items = fabric_get(f"/workspaces/{workspace_id}/{kind}", token)["value"]
    for item in items:
        if item["displayName"] == name:
            return item
    raise SystemExit(f"{kind[:-1]} {name} not found in workspace {workspace_id}: run the Fabric Terraform stack first")


def stage_items(target: Path, values: dict[str, str]) -> None:
    for folder in [
        *ROOT.glob("fabric/*.Notebook"),
        *ROOT.glob("fabric/*.DataPipeline"),
        *ROOT.glob("powerbi/*.SemanticModel"),
        *ROOT.glob("powerbi/*.Report"),
    ]:
        ignore = shutil.ignore_patterns(".pbi", "*.abf", "localSettings.json")
        shutil.copytree(folder, target / folder.name, ignore=ignore)
    for path in target.rglob("*"):
        if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.name == ".platform"):
            text = path.read_text(encoding="utf-8")
            new = text
            for key, value in values.items():
                new = new.replace(f"#{{{key}}}#", value)
            if new != text:
                path.write_text(new, encoding="utf-8")
    left = [p for p in target.rglob("*") if p.is_file() and "#{" in p.read_text(encoding="utf-8", errors="ignore")]
    if left:
        raise SystemExit(f"unreplaced placeholders in {[str(p.relative_to(target)) for p in left]}")


def build_artifacts(out: Path) -> tuple[Path, Path]:
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(out)], cwd=ROOT, check=True)
    wheel = next(out.glob("bilanzwerk-*.whl"))
    dbt_zip = out / "bilanzwerk-dbt.zip"
    with zipfile.ZipFile(dbt_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in (ROOT / "dbt").rglob("*"):
            rel = path.relative_to(ROOT / "dbt")
            if path.is_file() and rel.parts[0] not in ("target", "logs", "dbt_packages"):
                zf.write(path, rel)
    return wheel, dbt_zip


def upload(workspace_id: str, lakehouse_id: str, files: dict[str, Path], credential) -> None:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.storage.filedatalake import DataLakeServiceClient

    service = DataLakeServiceClient("https://onelake.dfs.fabric.microsoft.com", credential=credential)
    fs = service.get_file_system_client(workspace_id)
    # wheels/latest holds exactly one wheel: the notebooks install whatever is there.
    with contextlib.suppress(ResourceNotFoundError):
        fs.get_directory_client(f"{lakehouse_id}/Files/wheels/latest").delete_directory()
    for remote, local in files.items():
        client = fs.get_file_client(f"{lakehouse_id}/Files/{remote}")
        with local.open("rb") as fh:
            client.upload_data(fh, overwrite=True)
        print(f"uploaded Files/{remote}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--stage", choices=["dev", "prod"], required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--key-vault-uri", default=os.environ.get("BW_KEY_VAULT_URI", ""))
    parser.add_argument("--alert-email", default=os.environ.get("BW_ALERT_EMAIL", ""))
    parser.add_argument("--skip-upload", action="store_true", help="items only (no wheel, no dbt zip)")
    args = parser.parse_args()
    if not args.key_vault_uri or not args.alert_email:
        raise SystemExit("--key-vault-uri and --alert-email (or BW_KEY_VAULT_URI, BW_ALERT_EMAIL) are required")

    from azure.identity import DefaultAzureCredential
    from fabric_cicd import FabricWorkspace, publish_all_items

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    warehouse = item_by_name(args.workspace_id, "warehouses", "wh_bilanzwerk", token)
    lakehouse = item_by_name(args.workspace_id, "lakehouses", "lh_bilanzwerk", token)
    values = {
        "KEY_VAULT_URI": args.key_vault_uri,
        "ALERT_EMAIL": args.alert_email,
        "STAGE": args.stage,
        "SQL_ENDPOINT": warehouse["properties"]["connectionString"],
        "WAREHOUSE": "wh_bilanzwerk",
    }

    with tempfile.TemporaryDirectory() as tmp:
        staging, build = Path(tmp) / "items", Path(tmp) / "build"
        staging.mkdir()
        stage_items(staging, values)
        if not args.skip_upload:
            wheel, dbt_zip = build_artifacts(build)
            upload(
                args.workspace_id,
                lakehouse["id"],
                {
                    f"wheels/latest/{wheel.name}": wheel,
                    f"wheels/archive/{wheel.name}": wheel,
                    "dbt/bilanzwerk-dbt.zip": dbt_zip,
                },
                credential,
            )
        workspace = FabricWorkspace(
            workspace_id=args.workspace_id,
            environment=args.stage,
            repository_directory=str(staging),
            item_type_in_scope=ITEM_TYPES,
            token_credential=credential,
        )
        publish_all_items(workspace)
    print(f"published {', '.join(ITEM_TYPES)} to {args.stage} ({args.workspace_id})")


if __name__ == "__main__":
    main()
