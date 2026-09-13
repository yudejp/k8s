#!/usr/bin/env python3

import importlib.util
import io
import json
import gzip
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("longhorn-pv-backup.py")
SPEC = importlib.util.spec_from_file_location("longhorn_pv_backup", SCRIPT)
assert SPEC and SPEC.loader
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


class FakeKubectl:
    def __init__(self, objects):
        self.objects = objects

    def json(self, *args):
        if args[:2] == ("get", "pv"):
            return self.objects["pv"]
        if args[:2] == ("get", "pvc"):
            return self.objects["pvc"]
        if args[:2] == ("get", "volumes.longhorn.io"):
            return self.objects["volume"]
        if args[:2] == ("get", "pods"):
            return self.objects["pods"]
        raise AssertionError(args)


def objects():
    return {
        "pv": {
            "spec": {
                "capacity": {"storage": "10Gi"},
                "claimRef": {"namespace": "app", "name": "data", "uid": "claim-uid"},
                "csi": {
                    "driver": "driver.longhorn.io",
                    "fsType": "ext4",
                    "volumeHandle": "vol-1",
                },
                "volumeMode": "Filesystem",
            },
            "status": {"phase": "Bound"},
        },
        "pvc": {"metadata": {"uid": "claim-uid"}, "spec": {"volumeName": "pv-1"}},
        "volume": {
            "status": {
                "conditions": [{"type": "Scheduled", "status": "True"}],
                "currentNodeID": "node-1",
                "robustness": "healthy",
                "state": "attached",
            }
        },
        "pods": {"items": []},
    }


class BackupTests(unittest.TestCase):
    def test_resolves_bound_longhorn_pv(self):
        resolved = backup.validate_and_resolve(FakeKubectl(objects()), "pv-1", "longhorn-system")
        self.assertEqual(resolved["namespace"], "app")
        self.assertEqual(resolved["claim_name"], "data")
        self.assertEqual(resolved["node"], "node-1")
        self.assertEqual(resolved["robustness"], "healthy")
        self.assertEqual(resolved["scheduled"], "True")

    def test_rejects_non_longhorn_pv(self):
        fixtures = objects()
        fixtures["pv"]["spec"]["csi"]["driver"] = "example.invalid"
        with self.assertRaisesRegex(backup.BackupError, "not a Longhorn"):
            backup.validate_and_resolve(FakeKubectl(fixtures), "pv-1", "longhorn-system")

    def test_rejects_stale_claim_reference(self):
        fixtures = objects()
        fixtures["pvc"]["metadata"]["uid"] = "replacement-uid"
        with self.assertRaisesRegex(backup.BackupError, "UID mismatch"):
            backup.validate_and_resolve(FakeKubectl(fixtures), "pv-1", "longhorn-system")

    def test_detects_only_nonterminal_consumers(self):
        fixtures = objects()
        fixtures["pods"] = {
            "items": [
                {
                    "metadata": {"name": "writer"},
                    "spec": {"volumes": [{"persistentVolumeClaim": {"claimName": "data"}}]},
                    "status": {"phase": "Running"},
                },
                {
                    "metadata": {"name": "finished"},
                    "spec": {"volumes": [{"persistentVolumeClaim": {"claimName": "data"}}]},
                    "status": {"phase": "Succeeded"},
                },
            ]
        }
        self.assertEqual(backup.active_consumers(FakeKubectl(fixtures), "app", "data"), ["writer"])

    def test_manifest_is_read_only_and_pinned_to_attached_node(self):
        manifest = backup.pod_manifest("app", "backup-pod", "data", "busybox:test", "node-1", 900)
        spec = manifest["spec"]
        self.assertEqual(spec["nodeName"], "node-1")
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertTrue(spec["volumes"][0]["persistentVolumeClaim"]["readOnly"])
        self.assertTrue(spec["containers"][0]["volumeMounts"][0]["readOnly"])
        self.assertTrue(spec["containers"][0]["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(
            spec["containers"][0]["securityContext"]["capabilities"]["add"],
            ["DAC_READ_SEARCH"],
        )

    def test_hashing_writer_hashes_written_bytes(self):
        raw = io.BytesIO()
        writer = backup.HashingWriter(raw)
        writer.write(b"archive")
        self.assertEqual(writer.bytes_written, 7)
        self.assertEqual(
            writer.digest.hexdigest(),
            "0eb3e36bfb24dcd9bb1d1bece1531216b59539a8fde17ee80224af0653c92aa3",
        )

    def test_hashing_writer_supports_gzip_stream(self):
        raw = io.BytesIO()
        writer = backup.HashingWriter(raw)
        with gzip.GzipFile(fileobj=writer, mode="wb", mtime=0) as compressed:
            compressed.write(b"tar stream")
        self.assertEqual(gzip.decompress(raw.getvalue()), b"tar stream")
        self.assertEqual(writer.bytes_written, len(raw.getvalue()))

    def test_stream_archive_writes_and_hashes_gzip(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = io.BytesIO(b"tar payload")

            def poll(self):
                return 0

            def terminate(self):
                raise AssertionError("completed process must not be terminated")

            def wait(self):
                return 0

        kubectl = mock.Mock()
        kubectl.command.return_value = ["kubectl", "exec"]
        with tempfile.TemporaryDirectory() as directory:
            partial = Path(directory) / "archive.partial"
            with mock.patch.object(backup.subprocess, "Popen", return_value=FakeProcess()):
                digest, size = backup.stream_archive(
                    kubectl, "app", "backup-pod", partial, "gzip"
                )
            compressed = partial.read_bytes()
            self.assertEqual(gzip.decompress(compressed), b"tar payload")
            self.assertEqual(digest, hashlib.sha256(compressed).hexdigest())
            self.assertEqual(size, len(compressed))

    def test_metadata_write_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.json"
            backup.write_metadata(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})
            self.assertEqual(list(Path(directory).glob("*.partial.*")), [])

    def test_metadata_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.json"
            path.write_text("existing")
            with self.assertRaisesRegex(backup.BackupError, "refusing to overwrite"):
                backup.write_metadata(path, {"ok": True})
            self.assertEqual(path.read_text(), "existing")

    def test_detached_volume_reports_unknown_robustness(self):
        fixtures = objects()
        fixtures["volume"]["status"].update(
            {"state": "detached", "robustness": "unknown", "currentNodeID": ""}
        )
        resolved = backup.validate_and_resolve(
            FakeKubectl(fixtures), "pv-1", "longhorn-system"
        )
        self.assertEqual(resolved["state"], "detached")
        self.assertEqual(resolved["robustness"], "unknown")
        self.assertIsNone(resolved["node"])


if __name__ == "__main__":
    unittest.main()
