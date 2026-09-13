#!/usr/bin/env python3
"""Stream a filesystem-level Longhorn PV backup through kubectl."""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Sequence


LONGHORN_DRIVER = "driver.longhorn.io"
DEFAULT_LONGHORN_NAMESPACE = "longhorn-system"
DEFAULT_IMAGE = "busybox:1.37.0"
DEFAULT_POD_DEADLINE_SECONDS = 24 * 60 * 60


class BackupError(RuntimeError):
    pass


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class Kubectl:
    def __init__(self, binary: str, context: str | None) -> None:
        self.base = [binary]
        if context:
            self.base.extend(["--context", context])

    def command(self, *args: str) -> list[str]:
        return [*self.base, *args]

    def run(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                self.command(*args),
                input=input_bytes,
                check=check,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
            )
        except FileNotFoundError as exc:
            raise BackupError(f"kubectl executable not found: {self.base[0]}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            raise BackupError(
                f"kubectl command failed ({' '.join(self.command(*args))}){detail}"
            ) from exc

    def json(self, *args: str) -> dict[str, Any]:
        result = self.run(*args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BackupError(
                f"kubectl returned invalid JSON ({' '.join(self.command(*args))})"
            ) from exc


def nested(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = obj
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def longhorn_condition(volume: dict[str, Any], condition_type: str) -> dict[str, Any] | None:
    for condition in nested(volume, "status", "conditions", default=[]):
        if condition.get("type") == condition_type:
            return condition
    return None


def validate_and_resolve(
    kubectl: Kubectl, pv_name: str, longhorn_namespace: str
) -> dict[str, Any]:
    pv = kubectl.json("get", "pv", pv_name, "-o", "json")
    phase = nested(pv, "status", "phase")
    if phase != "Bound":
        raise BackupError(f"PV {pv_name!r} is not Bound (phase={phase!r})")

    csi = nested(pv, "spec", "csi", default={})
    if csi.get("driver") != LONGHORN_DRIVER:
        raise BackupError(
            f"PV {pv_name!r} is not a Longhorn CSI volume "
            f"(driver={csi.get('driver')!r})"
        )

    volume_mode = nested(pv, "spec", "volumeMode", default="Filesystem")
    if volume_mode != "Filesystem":
        raise BackupError(
            f"PV {pv_name!r} uses volumeMode={volume_mode!r}; only Filesystem is supported"
        )

    claim_ref = nested(pv, "spec", "claimRef", default={})
    namespace = claim_ref.get("namespace")
    claim_name = claim_ref.get("name")
    if not namespace or not claim_name:
        raise BackupError(f"PV {pv_name!r} has no namespaced claimRef")

    pvc = kubectl.json("get", "pvc", claim_name, "-n", namespace, "-o", "json")
    if nested(pvc, "spec", "volumeName") != pv_name:
        raise BackupError(
            f"PVC {namespace}/{claim_name} no longer points to PV {pv_name!r}"
        )
    expected_uid = claim_ref.get("uid")
    actual_uid = nested(pvc, "metadata", "uid")
    if expected_uid and actual_uid != expected_uid:
        raise BackupError(
            f"PVC UID mismatch for {namespace}/{claim_name}; refusing a stale claimRef"
        )

    handle = csi.get("volumeHandle")
    if not handle:
        raise BackupError(f"PV {pv_name!r} has no CSI volumeHandle")
    volume = kubectl.json(
        "get", "volumes.longhorn.io", handle, "-n", longhorn_namespace, "-o", "json"
    )

    scheduled = longhorn_condition(volume, "Scheduled")
    return {
        "pv": pv,
        "pvc": pvc,
        "volume": volume,
        "pv_name": pv_name,
        "namespace": namespace,
        "claim_name": claim_name,
        "volume_handle": handle,
        "capacity": nested(pv, "spec", "capacity", "storage"),
        "filesystem": csi.get("fsType") or csi.get("volumeAttributes", {}).get("fsType"),
        "state": nested(volume, "status", "state"),
        "robustness": nested(volume, "status", "robustness"),
        "scheduled": scheduled.get("status") if scheduled else None,
        "scheduling_message": scheduled.get("message") if scheduled else None,
        "node": nested(volume, "status", "currentNodeID") or None,
    }


def active_consumers(kubectl: Kubectl, namespace: str, claim_name: str) -> list[str]:
    pods = kubectl.json("get", "pods", "-n", namespace, "-o", "json")
    consumers: list[str] = []
    for pod in pods.get("items", []):
        phase = nested(pod, "status", "phase")
        if phase in {"Succeeded", "Failed"}:
            continue
        for volume in nested(pod, "spec", "volumes", default=[]):
            if nested(volume, "persistentVolumeClaim", "claimName") == claim_name:
                consumers.append(nested(pod, "metadata", "name", default="<unknown>"))
                break
    return consumers


def safe_name(pv_name: str) -> str:
    suffix = re.sub(r"[^a-z0-9-]", "-", pv_name.lower()).strip("-")[-30:]
    random_part = secrets.token_hex(3)
    return f"longhorn-pv-backup-{suffix}-{random_part}"[:63].rstrip("-")


def pod_manifest(
    namespace: str, pod_name: str, claim_name: str, image: str, node: str | None,
    active_deadline_seconds: int,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "activeDeadlineSeconds": active_deadline_seconds,
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [
            {
                "name": "backup",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "command": ["sh", "-c", "while true; do sleep 3600; done"],
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"], "add": ["DAC_READ_SEARCH"]},
                    "readOnlyRootFilesystem": True,
                    "runAsUser": 0,
                },
                "volumeMounts": [
                    {"name": "source", "mountPath": "/volume", "readOnly": True}
                ],
            }
        ],
        "volumes": [
            {
                "name": "source",
                "persistentVolumeClaim": {"claimName": claim_name, "readOnly": True},
            }
        ],
    }
    if node:
        spec["nodeName"] = node
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {"app.kubernetes.io/name": "longhorn-pv-backup"},
        },
        "spec": spec,
    }


class HashingWriter:
    def __init__(self, raw: BinaryIO) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()
        self.bytes_written = 0

    def write(self, data: bytes) -> int:
        written = self.raw.write(data)
        self.digest.update(data[:written])
        self.bytes_written += written
        return written

    def flush(self) -> None:
        self.raw.flush()


def stream_archive(
    kubectl: Kubectl, namespace: str, pod_name: str, partial: Path, compression: str
) -> tuple[str, int]:
    command = kubectl.command(
        "exec", "-n", namespace, pod_name, "--", "tar", "-C", "/volume", "-cf", "-", "."
    )
    with tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr_file)
        except FileNotFoundError as exc:
            raise BackupError(f"kubectl executable not found: {kubectl.base[0]}") from exc
        assert process.stdout is not None

        try:
            with partial.open("xb") as raw:
                writer = HashingWriter(raw)
                if compression == "gzip":
                    with gzip.GzipFile(
                        fileobj=writer, mode="wb", compresslevel=6, mtime=0
                    ) as output:
                        while chunk := process.stdout.read(1024 * 1024):
                            output.write(chunk)
                else:
                    while chunk := process.stdout.read(1024 * 1024):
                        writer.write(chunk)
                raw.flush()
                os.fsync(raw.fileno())
        except BaseException:
            if process.poll() is None:
                process.terminate()
            process.wait()
            raise

        return_code = process.wait()
        stderr_file.seek(0)
        stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
        if return_code != 0:
            raise BackupError(
                f"tar stream failed with exit code {return_code}"
                + (f": {stderr}" if stderr else "")
            )
        return writer.digest.hexdigest(), writer.bytes_written


def commit_no_replace(partial: Path, destination: Path) -> None:
    """Atomically publish a same-directory file without replacing a destination."""
    try:
        os.link(partial, destination)
    except FileExistsError as exc:
        raise BackupError(
            f"output appeared while backing up; refusing to overwrite: {destination}"
        ) from exc
    except OSError as exc:
        raise BackupError(
            f"cannot atomically publish {destination}; the destination filesystem "
            f"must support hard links: {exc}"
        ) from exc
    partial.unlink()


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    partial = path.with_name(f".{path.name}.partial.{os.getpid()}")
    try:
        with partial.open("x", encoding="utf-8") as output:
            json.dump(metadata, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        commit_no_replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def default_output(pv_name: str, compression: str) -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extension = ".tar.gz" if compression == "gzip" else ".tar"
    return Path(f"{pv_name}-{timestamp}{extension}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Back up one Longhorn filesystem PV to a local tar archive via kubectl."
    )
    result.add_argument("pv", help="exact PersistentVolume name")
    result.add_argument("-o", "--output", type=Path, help="local archive path")
    result.add_argument("--compression", choices=("gzip", "none"), default="gzip")
    result.add_argument("--context", help="kubectl context")
    result.add_argument("--kubectl", default="kubectl", help="kubectl executable")
    result.add_argument("--longhorn-namespace", default=DEFAULT_LONGHORN_NAMESPACE)
    result.add_argument("--image", default=DEFAULT_IMAGE, help="temporary backup Pod image")
    result.add_argument("--timeout", type=int, default=600, help="Pod readiness timeout in seconds")
    result.add_argument(
        "--allow-live",
        action="store_true",
        help="allow a crash-consistent archive while active Pods use the PVC",
    )
    result.add_argument(
        "--allow-unhealthy",
        action="store_true",
        help="allow backup when Longhorn robustness is not healthy",
    )
    result.add_argument("--keep-pod", action="store_true", help="do not delete the temporary Pod")
    result.add_argument(
        "--dry-run", action="store_true", help="validate and print the Pod manifest without creating it"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.timeout <= 0:
        raise BackupError("--timeout must be greater than zero")

    kubectl = Kubectl(args.kubectl, args.context)
    resolved = validate_and_resolve(kubectl, args.pv, args.longhorn_namespace)
    if resolved["state"] not in {"attached", "detached"}:
        raise BackupError(
            f"Longhorn volume is in transitional state {resolved['state']!r}; wait until it is attached or detached"
        )
    if resolved["scheduled"] == "False":
        detail = f": {resolved['scheduling_message']}" if resolved["scheduling_message"] else ""
        raise BackupError(f"Longhorn reports that the volume cannot be scheduled{detail}")
    health_is_expected = resolved["robustness"] == "healthy" or (
        resolved["state"] == "detached" and resolved["robustness"] == "unknown"
    )
    if not health_is_expected and not args.allow_unhealthy:
        raise BackupError(
            f"Longhorn volume robustness is {resolved['robustness']!r}; "
            "use --allow-unhealthy only after reviewing volume health"
        )

    consumers = active_consumers(kubectl, resolved["namespace"], resolved["claim_name"])
    if consumers and not args.allow_live:
        raise BackupError(
            "PVC is referenced by active Pod(s): "
            + ", ".join(consumers)
            + ". Stop/quiesce them first, or explicitly use --allow-live for a crash-consistent backup."
        )
    if consumers:
        eprint("WARNING: active writers may make this filesystem archive application-inconsistent.")

    pod_name = safe_name(args.pv)
    manifest = pod_manifest(
        resolved["namespace"],
        pod_name,
        resolved["claim_name"],
        args.image,
        resolved["node"],
        DEFAULT_POD_DEADLINE_SECONDS,
    )
    if args.dry_run:
        print(json.dumps({"resolved": {k: v for k, v in resolved.items() if k not in {"pv", "pvc", "volume"}}, "activeConsumers": consumers, "pod": manifest}, indent=2))
        return 0

    output = args.output or default_output(args.pv, args.compression)
    output = output.expanduser().resolve()
    metadata_path = Path(f"{output}.json")
    if output.exists() or metadata_path.exists():
        raise BackupError(f"output already exists; refusing to overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.name}.partial.{os.getpid()}")
    if partial.exists():
        raise BackupError(f"partial output already exists: {partial}")

    pod_created = False

    def interrupted(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"received signal {signum}")

    previous_sigterm = signal.signal(signal.SIGTERM, interrupted)
    try:
        eprint(
            f"PV {args.pv} -> PVC {resolved['namespace']}/{resolved['claim_name']} "
            f"(Longhorn: {resolved['robustness']}, node: {resolved['node'] or 'scheduler-selected'})"
        )
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        kubectl.run("create", "-f", "-", input_bytes=manifest_bytes)
        pod_created = True
        eprint(f"Waiting for temporary Pod {resolved['namespace']}/{pod_name} ...")
        kubectl.run(
            "wait",
            "--for=condition=Ready",
            f"pod/{pod_name}",
            "-n",
            resolved["namespace"],
            f"--timeout={args.timeout}s",
            capture_output=False,
        )
        eprint(f"Streaming archive to {output} ...")
        sha256, bytes_written = stream_archive(
            kubectl, resolved["namespace"], pod_name, partial, args.compression
        )
        commit_no_replace(partial, output)
        created_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        metadata = {
            "archive": str(output),
            "archiveBytes": bytes_written,
            "compression": args.compression,
            "createdAt": created_at,
            "sha256": sha256,
            "source": {
                "capacity": resolved["capacity"],
                "filesystem": resolved["filesystem"],
                "longhornNode": resolved["node"],
                "longhornRobustness": resolved["robustness"],
                "longhornState": resolved["state"],
                "namespace": resolved["namespace"],
                "persistentVolume": args.pv,
                "persistentVolumeClaim": resolved["claim_name"],
                "volumeHandle": resolved["volume_handle"],
            },
        }
        write_metadata(metadata_path, metadata)
        eprint(f"Backup complete: {output}")
        eprint(f"SHA-256: {sha256}")
        return 0
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        if partial.exists():
            partial.unlink()
        if pod_created and not args.keep_pod:
            eprint(f"Deleting temporary Pod {resolved['namespace']}/{pod_name} ...")
            try:
                cleanup = kubectl.run(
                    "delete",
                    "pod",
                    pod_name,
                    "-n",
                    resolved["namespace"],
                    "--ignore-not-found=true",
                    "--wait=false",
                    check=False,
                )
                if cleanup.returncode != 0:
                    stderr = (cleanup.stderr or b"").decode("utf-8", errors="replace").strip()
                    eprint(f"WARNING: failed to delete exact Pod {pod_name}: {stderr}")
            except BackupError as exc:
                eprint(f"WARNING: failed to delete exact Pod {pod_name}: {exc}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupError as exc:
        eprint(f"ERROR: {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        eprint("ERROR: interrupted")
        raise SystemExit(130)
