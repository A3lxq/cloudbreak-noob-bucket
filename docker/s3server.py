#!/usr/bin/env python3
"""
A minimal, dependency-free S3-compatible object storage server.

MinIO's community binaries were pulled from distribution (dl.min.io
now returns 410 Gone for the server/client downloads this box
originally relied on) -- this hand-rolled replacement serves the same
purpose for the challenge: real HTTP GETs for bucket listing and
object retrieval, with one bucket gated behind a credential check.

NOT a real S3 implementation -- no SigV4 signature verification, just
a presence/match check on the Authorization header's Credential=...
access key, which both `aws s3` and `mc` always send in that exact
shape regardless of whether the server actually verifies the
signature. Good enough for the challenge's actual security property
(the private bucket is unreachable without the leaked credential);
not a general-purpose S3 mock.
"""
import os
import re
import socketserver
import html
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

DATA_ROOT = "/data"
PUBLIC_BUCKETS = {"public-assets", "nimbus-freight-backups"}
ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "nimbus-deploy-svc")

_CRED_RE = re.compile(r"Credential=([^/,\s]+)/")


def _authorized(headers) -> bool:
    auth = headers.get("Authorization", "")
    m = _CRED_RE.search(auth)
    return bool(m) and m.group(1) == ACCESS_KEY


def _list_objects_xml(bucket: str, root: str) -> bytes:
    entries = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            key = os.path.relpath(full, root).replace(os.sep, "/")
            size = os.path.getsize(full)
            mtime = datetime.fromtimestamp(os.path.getmtime(full), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            entries.append(
                f"<Contents><Key>{html.escape(key)}</Key><LastModified>{mtime}</LastModified>"
                f'<ETag>"-"</ETag><Size>{size}</Size><StorageClass>STANDARD</StorageClass></Contents>'
            )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>{html.escape(bucket)}</Name><Prefix></Prefix>"
        f"<KeyCount>{len(entries)}</KeyCount><MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>"
        + "".join(entries)
        + "</ListBucketResult>"
    )
    return body.encode()


def _access_denied_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>"
    ).encode()


def _no_such_key_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Error><Code>NoSuchKey</Code><Message>The specified key does not exist.</Message></Error>"
    ).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep container logs quiet; the challenge doesn't need access logs

    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        if not path:
            self.send_response(200)
            self.end_headers()
            return

        parts = path.split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""

        bucket_root = os.path.join(DATA_ROOT, bucket)
        if not os.path.isdir(bucket_root):
            self.send_response(404)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(_no_such_key_xml())
            return

        if bucket not in PUBLIC_BUCKETS and not _authorized(self.headers):
            self.send_response(403)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(_access_denied_xml())
            return

        if not key:
            body = _list_objects_xml(bucket, bucket_root)
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        full_path = os.path.normpath(os.path.join(bucket_root, key))
        if not full_path.startswith(os.path.normpath(bucket_root) + os.sep) or not os.path.isfile(full_path):
            self.send_response(404)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(_no_such_key_xml())
            return

        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, __import__("http.server", fromlist=["HTTPServer"]).HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(os.environ.get("S3_PORT", "9000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
