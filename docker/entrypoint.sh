#!/bin/bash
set -e

: "${CTF_SECRET:?CTF_SECRET must be set}"
export CTF_SECRET

flag() { python3 /opt/generate_flags.py "$1"; }

DEPLOY_PASSWORD="Fr3ight-Deploy-2024!"  # fixed/narrative -- discoverable via the leaked app-config.json, same for every team by design

echo "[*] Initializing Nimbus Freight Object Storage..."

# --- Linux account (also the SSH foothold, password reused from the --
# --- leaked storage credential) -----------------------------------------
if ! id nimbus-deploy &>/dev/null; then
    useradd -m -s /bin/bash nimbus-deploy
fi
echo "nimbus-deploy:${DEPLOY_PASSWORD}" | chpasswd
mkdir -p /run/sshd
ssh-keygen -A

# --- Flag substitution in the seed content, before it's uploaded --------
sed -i "s/FLAG1_PLACEHOLDER/$(flag 1)/" /opt/seed/public-assets/welcome.txt
sed -i "s/FLAG2_PLACEHOLDER/$(flag 2)/" /opt/seed/public-assets/README.md
sed -i "s/FLAG3_PLACEHOLDER/$(flag 3)/" /opt/seed/public-assets/logs/deploy.log
sed -i "s/FLAG4_PLACEHOLDER/$(flag 4)/" /opt/seed/backups/README.txt
sed -i "s/FLAG5_PLACEHOLDER/$(flag 5)/" /opt/seed/backups/app-config.json
sed -i "s/FLAG6_PLACEHOLDER/$(flag 6)/" /opt/seed/private/memo.txt
sed -i "s/FLAG7_PLACEHOLDER/$(flag 7)/" /opt/seed/private/employee_portal_creds.txt

# --- Object storage: a small hand-rolled S3-compatible server (see ------
# --- s3server.py's own docstring -- MinIO's community binaries were ------
# --- pulled from distribution, dl.min.io now 410s). The "private" --------
# --- bucket is gated behind the leaked access key; the other two are -----
# --- unauthenticated. ------------------------------------------------------
mkdir -p /data/public-assets /data/nimbus-freight-backups /data/nimbus-freight-private
cp -r /opt/seed/public-assets/. /data/public-assets/
cp -r /opt/seed/backups/. /data/nimbus-freight-backups/
cp -r /opt/seed/private/. /data/nimbus-freight-private/

S3_ACCESS_KEY="nimbus-deploy-svc" python3 /opt/s3server.py &

# --- SSH foothold flag ---------------------------------------------------
HOME_DIR="/home/nimbus-deploy"
echo "$(flag 8)" > "$HOME_DIR/user.txt"
cat << 'EOF' > "$HOME_DIR/notes.txt"
To-do:
- Stop reusing the storage credential as my own login password.
- Ops gave me passwordless sudo on 'tar' for pulling backup archives
  off this box without bugging anyone. Never got around to asking for
  anything narrower.
EOF
chown -R nimbus-deploy:nimbus-deploy "$HOME_DIR"
chmod 600 "$HOME_DIR/user.txt"
chmod 644 "$HOME_DIR/notes.txt"

# --- A root-only file, reachable via the 'tar' GTFOBins trick before --
# --- going for a full root shell (flag 9) --------------------------------
mkdir -p /var/backups
cat << EOF > /var/backups/storage_audit.log
[audit] nimbus-deploy-svc credential still has root-equivalent MinIO access
[audit] rotation ticket opened, never closed

Flag 9: $(flag 9)
EOF
chown root:root /var/backups/storage_audit.log
chmod 600 /var/backups/storage_audit.log

# --- sudoers: nimbus-deploy may run 'tar' as root, no password ----------
cat << 'EOF' > /etc/sudoers.d/nimbus-deploy
nimbus-deploy ALL=(ALL) NOPASSWD: /usr/bin/tar
EOF
chmod 440 /etc/sudoers.d/nimbus-deploy

# --- Final root flag ------------------------------------------------------
echo "$(flag 10)" > /root/root.txt
chmod 600 /root/root.txt

exec /usr/sbin/sshd -D -e
