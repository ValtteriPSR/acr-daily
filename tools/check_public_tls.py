"""Read-only public HTTPS probe, including a stale Windows intermediate model.

Does not modify Windows certificate stores or disable certificate validation.
"""
import argparse
import datetime as dt
import hashlib
import http.client
import json
import ssl
import urllib.parse
import urllib.request

CERTIFICATES = {
    'x1': ('https://letsencrypt.org/certs/isrgrootx1.pem',
           '96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6'),
    'old_x2': ('https://letsencrypt.org/certs/isrg-root-x2-cross-signed.pem',
               '8b05b68cc659e5ed0fcb38f2c942fbfd200e6f2ff9f85d63c6994ef5e0b02701'),
}


def certificate(name):
    url, expected = CERTIFICATES[name]
    with urllib.request.urlopen(url, timeout=20) as response:
        pem = response.read(16384).decode('ascii')
    digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    if digest != expected:
        raise ValueError('Unexpected public CA certificate fingerprint: ' + name)
    return pem


def context(legacy=False):
    standard = ssl.create_default_context()
    if not legacy:
        return standard
    # Windows may retain this expired cross-sign as a trusted intermediate.
    # Use an isolated store: the valid X1 root plus the historical expired X2.
    # Python 3.13 treats trusted intermediates as possible trust anchors.
    model = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    model.verify_flags = standard.verify_flags | ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_STRICT
    model.load_verify_locations(cadata=certificate('x1') + certificate('old_x2'))
    return model


def probe(origin, legacy=False):
    parsed = urllib.parse.urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('An HTTPS origin is required')
    ctx = context(legacy)
    assert ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                            context=ctx, timeout=20)
    try:
        connection.connect()
        peer = connection.sock.getpeercert()
        connection.request('GET', '/healthz', headers={'User-Agent': 'ACR-TLS-Diagnostic/1.0'})
        response = connection.getresponse()
        response.read(4096)
        if response.status != 200:
            raise ValueError('HTTPS health status: ' + str(response.status))
        return {'ok': True, 'mode': 'stale-x2' if legacy else 'system-default',
                'issuer': peer['issuer'], 'notBefore': peer['notBefore'],
                'notAfter': peer['notAfter'], 'httpStatus': response.status}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://acr.projectsimracing.pl')
    parser.add_argument('--check-legacy-x2', action='store_true')
    args = parser.parse_args()
    print(json.dumps({'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                      'openssl': ssl.OPENSSL_VERSION}), flush=True)
    failed = False
    for legacy in ([False, True] if args.check_legacy_x2 else [False]):
        try:
            print(json.dumps(probe(args.url, legacy)), flush=True)
        except Exception as error:
            failed = True
            print(json.dumps({'ok': False, 'mode': 'stale-x2' if legacy else 'system-default',
                              'errorType': type(error).__name__, 'error': str(error)}), flush=True)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
