"""CADDY_BIN=/path/to/caddy uv run --with pyyaml python tests/casdoor/test_storage_proxy.py"""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from test_chart import manifests, resource


CADDY = os.environ.get("CADDY_BIN") or shutil.which("caddy")


class Upstream(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        self.requests.append((self.command, self.path, dict(self.headers)))
        body = json.dumps({"path": self.path, "headers": dict(self.headers)}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_HEAD = do_GET

    def log_message(self, *_):
        pass


@unittest.skipUnless(CADDY, "Set CADDY_BIN to run Caddy integration tests")
class StorageProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.tmp.name)
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        docs = manifests({"storageProxy": {"enabled": True, "port": cls.port}}, with_credentials=False)
        data = resource(docs, "ConfigMap", "casdoor-storage-proxy")["data"]
        cls.config = cls.directory / "Caddyfile"
        cls.config.write_text(data["Caddyfile"])
        cls.script = cls.directory / "start.sh"
        cls.script.write_text(data["start.sh"].replace("/etc/caddy/Caddyfile", str(cls.config)))
        cls.env = {**os.environ, "S3_BUCKET": "casdoor",
                   "S3_ENDPOINT": f"http://127.0.0.1:{cls.upstream.server_port}",
                   "XDG_DATA_HOME": str(cls.directory / "data"),
                   "XDG_CONFIG_HOME": str(cls.directory / "config"),
                   "PATH": str(Path(CADDY).resolve().parent) + os.pathsep + os.environ["PATH"]}
        cls.log = (cls.directory / "caddy.log").open("w+")
        cls.process = subprocess.Popen(["/bin/sh", str(cls.script)], env=cls.env,
                                       stdout=cls.log, stderr=cls.log)
        for _ in range(100):
            if cls.process.poll() is not None:
                break
            try:
                if cls.request("/_proxy/health")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.05)
        cls.log.seek(0)
        output = cls.log.read()
        cls.tearDownClass()
        raise AssertionError(f"Caddy did not become ready: {output}")

    @classmethod
    def tearDownClass(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
            cls.process.wait(timeout=5)
        cls.log.close()
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.thread.join(timeout=5)
        cls.tmp.cleanup()

    @classmethod
    def request(cls, path, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=2)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_objects_get_head_and_credentials_are_removed(self):
        status, body = self.request("/casdoor/avatar.png?acl&list-type=2&X-Amz-Signature=secret", headers={
            "Authorization": "AWS4-HMAC-SHA256 secret", "Cookie": "session=secret",
            "X-Amz-Security-Token": "secret", "X-Minio-Test": "secret", "Host": "files.example.com"})
        self.assertEqual(status, 200)
        echoed = json.loads(body)
        self.assertEqual(echoed["path"], "/casdoor/avatar.png")
        headers = {k.lower(): v for k, v in echoed["headers"].items()}
        self.assertEqual(headers["host"], f"127.0.0.1:{self.upstream.server_port}")
        for key in ("authorization", "cookie", "x-amz-security-token", "x-minio-test"):
            self.assertNotIn(key, headers)
        self.assertEqual(self.request("/casdoor/avatar.png", "HEAD"), (200, b""))
        self.assertEqual(Upstream.requests[-1][:2], ("HEAD", "/casdoor/avatar.png"))

    def test_object_names_keep_their_original_url_encoding(self):
        for path in ("/casdoor/photo%20name.png", "/casdoor/%E5%A4%B4%E5%83%8F.png",
                     "/casdoor/image%3Fname.png", "/casdoor/image%23name.png",
                     "/casdoor/%3Flist-type=2"):
            with self.subTest(path=path):
                status, body = self.request(path + "?acl&list-type=2")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["path"], path)

    def test_other_buckets_lists_writes_and_traversal_never_reach_silo(self):
        count = len(Upstream.requests)
        cases = [("GET", path) for path in (
            "/", "/?list-type=2", "/casdoor", "/casdoor/?list-type=2", "/private/avatar.png",
            "/minio/admin/v3/info", "/casdoor/../private/secret", "/casdoor/./avatar.png",
            "/casdoor/%2e%2e/private/secret", "/casdoor/%252e%252e/private/secret",
            "/casdoor/..%2fprivate/secret", "/casdoor/..%5cprivate/secret",
            "/casdoor//../private/secret", "/casdoor///?list-type=2",
        )] + [(method, "/casdoor/avatar.png") for method in ("PUT", "POST", "DELETE", "PATCH", "OPTIONS")]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(path, method)[0], 404)
                self.assertEqual(len(Upstream.requests), count)

    def test_invalid_environment_fails_before_caddy_starts(self):
        cases = [{"S3_BUCKET": value} for value in (
            "", "..", "../private", "casdoor/../../private", "casdoor\nrespond 200", "a" * 64,
        )] + [{"S3_ENDPOINT": value} for value in (
            "", "ftp://silo:9000", "http://silo:9000/casdoor", "http://user:password@silo:9000",
            "http://silo:9000\nrespond 200", "http://silo:9000?bucket=private",
        )]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = subprocess.run(["/bin/sh", str(self.script)], env={**self.env, **overrides},
                                        capture_output=True, text=True, timeout=3)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("serving initial configuration", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
