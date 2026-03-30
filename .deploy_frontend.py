import paramiko
import os
import time

HOSTNAME = "137.220.63.222"
USERNAME = "root"
PASSWORD = "S)j4(PF@i#GC7C$g"
REMOTE_DIR = "/opt/gex_dashboard"

def run_cmd(ssh, cmd):
    print(f"\nCMD: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode()
    if out: print(out[:2000])
    if err: print(f"STDERR: {err[:500]}")

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOSTNAME, username=USERNAME, password=PASSWORD)
    print("Connected!")

    sftp = ssh.open_sftp()

    # 1. Upload backend main.py
    sftp.put("/Users/paolo/Desktop/GEX 4.0/backend/main.py",
             f"{REMOTE_DIR}/backend/main.py")
    print("Uploaded main.py")

    # 2. Upload frontend dist
    local_dist = "/Users/paolo/Desktop/GEX 4.0/frontend/dist"
    remote_dist = f"{REMOTE_DIR}/frontend/dist"
    
    # Clear old dist
    run_cmd(ssh, f"rm -rf {remote_dist} && mkdir -p {remote_dist}/_assets")
    
    for root, dirs, files in os.walk(local_dist):
        for f in files:
            local_path = os.path.join(root, f)
            rel = os.path.relpath(local_path, local_dist)
            remote_path = f"{remote_dist}/{rel}"
            remote_dir = os.path.dirname(remote_path)
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                run_cmd(ssh, f"mkdir -p {remote_dir}")
            sftp.put(local_path, remote_path)
            print(f"  Uploaded: {rel}")

    sftp.close()
    print("\nAll files uploaded.")

    # 3. Update Nginx config with API+WS proxy
    nginx_conf = """
server {
    listen 80;
    server_name _;
    
    root /opt/gex_dashboard/frontend/dist;
    index index.html;

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://127.0.0.1:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # Frontend SPA
    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""
    run_cmd(ssh, f"cat << 'NGINX_EOF' > /etc/nginx/sites-available/default\n{nginx_conf}\nNGINX_EOF")
    
    # 4. Test Nginx config
    run_cmd(ssh, "nginx -t")
    
    # 5. Restart services (NOT daemons — they stay isolated)
    run_cmd(ssh, "systemctl restart nginx")
    run_cmd(ssh, "systemctl restart gex_api")
    
    time.sleep(3)
    
    # 6. Verify
    run_cmd(ssh, "systemctl status gex_api --no-pager -l | head -15")
    run_cmd(ssh, "curl -s http://localhost:8000/api/symbols | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/api/symbols")
    run_cmd(ssh, "curl -s http://localhost:8000/api/candles/US500-F?interval=1m\\&limit=3 | python3 -m json.tool 2>/dev/null || curl -s 'http://localhost:8000/api/candles/US500-F?interval=1m&limit=3'")
    run_cmd(ssh, "curl -s http://localhost/api/symbols | head -200")  # test through Nginx
    
    # Check daemons are still running (isolation check)
    run_cmd(ssh, "systemctl is-active gex_ctrader gex_tradier")

    ssh.close()
    print("\nDeployment complete!")

if __name__ == "__main__":
    main()
