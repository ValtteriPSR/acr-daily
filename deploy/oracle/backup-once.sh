#!/bin/bash
# Root-only, manually invoked snapshot. No scheduler or Google Drive integration.
set -euo pipefail
umask 077
: "${ACR_BACKUP_NAMESPACE:?Set the Object Storage namespace}"
export ACR_BACKUP_NAMESPACE
export ACR_BACKUP_BUCKET="${ACR_BACKUP_BUCKET:-acr-migration-backups}"
install -d -m 0700 /opt/acr/backups
snapshot=$(mktemp -d /opt/acr/backups/cutover.XXXXXXXX)
trap 'rm -rf "$snapshot"' EXIT
podman exec acr-postgres pg_dump -U postgres -d acr_club --format=custom --no-owner --no-acl > "$snapshot/club.dump"
podman exec -i acr-postgres pg_restore --list < "$snapshot/club.dump" > "$snapshot/dump-contents.txt"
cp -a /opt/acr/production.env /opt/acr/gateway.env /opt/acr/postgres.env /opt/acr/local-database.env /opt/acr/Caddyfile "$snapshot/"
cp -a /etc/containers/systemd "$snapshot/units"
printf '%s\n' 760a085795329d1d2372cb6abb9ac1db7ad56e49 > "$snapshot/source-commit.txt"
archive=/opt/acr/backups/oracle-production-latest.tar.gz
tar -czf "$archive.tmp" -C "$snapshot" .
mv "$archive.tmp" "$archive"
python3 - <<'PY'
import base64, datetime, hashlib, json, os, uuid
from pathlib import Path
import oci
archive=Path('/opt/acr/backups/oracle-production-latest.tar.gz')
data=archive.read_bytes()
sha=hashlib.sha256(data).hexdigest()
name='cutover/'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex+'.tar.gz'
signer=oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
client=oci.object_storage.ObjectStorageClient(config={},signer=signer)
client.put_object(os.environ['ACR_BACKUP_NAMESPACE'],os.environ['ACR_BACKUP_BUCKET'],name,data,
    content_type='application/gzip',content_md5=base64.b64encode(hashlib.md5(data).digest()).decode(),
    opc_meta={'sha256':sha},if_none_match='*')
manifest={'object':name,'sha256':sha,'size':len(data)}
Path('/opt/acr/backups/uploaded-manifest.json').write_text(json.dumps(manifest))
print(json.dumps(manifest))
PY
