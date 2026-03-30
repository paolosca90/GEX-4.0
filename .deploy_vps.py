import paramiko
import os
import tarfile
import time

HOSTNAME = "137.220.63.222"
USERNAME = "root"
PASSWORD = "S)j4(PF@i#GC7C$g"
LOCAL_DIR = "/Users/paolo/Desktop/GEX 4.0"
TAR_FILE = "/Users/paolo/Desktop/GEX 4.0/gex_deploy.tar.gz"
REMOTE_DIR = "/opt/gex_dashboard"

def make_tarfile(output_filename, source_dir):
    print("Compressing project files (ignoring large deps)...")
    with tarfile.open(output_filename, "w:gz") as tar:
        for root, dirs, files in os.walk(source_dir):
            if 'node_modules' in root or 'venv' in root or '.git' in root or 'dist' not in root and 'frontend' in root and 'src' not in root and 'public' not in root and root != source_dir + '/frontend':
                continue
                
            for file in files:
                if file.endswith('.tar.gz') or file == '.env' or file == '.setup_vps.py':
                    continue
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, source_dir)
                try:
                    tar.add(file_path, arcname=arc_name)
                except Exception as e:
                    pass
    print("Archive created.")

def deploy():
    make_tarfile(TAR_FILE, LOCAL_DIR)
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting to Vultr VPS...")
    try:
        ssh.connect(HOSTNAME, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # 1. Upload the tarball
        sftp = ssh.open_sftp()
        print("Uploading archive...")
        sftp.put(TAR_FILE, "/tmp/gex_deploy.tar.gz")
        sftp.close()
        print("Upload complete.")
        
        # 2. Extract on server
        def run_cmd(cmd):
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            stdout.channel.recv_exit_status()
            print(stdout.read().decode())
        
        run_cmd(f"mkdir -p {REMOTE_DIR} && tar -xzf /tmp/gex_deploy.tar.gz -C {REMOTE_DIR}")
        
        # 3. Setup Python Backend Environment
        run_cmd(f"cd {REMOTE_DIR}/backend && apt-get install python3-venv -y && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt || ./venv/bin/pip install fastapi uvicorn asyncpg websockets httpx pyfix simplefix pandas numpy pytz schedule")
        
        # 4. Setup Systemd Services
        fastapi_service = f"""
[Unit]
Description=GEX FastAPI Server
After=network.target

[Service]
User=root
WorkingDirectory={REMOTE_DIR}/backend
ExecStart={REMOTE_DIR}/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
"""

        ctrader_service = f"""
[Unit]
Description=GEX cTrader Daemon
After=network.target

[Service]
User=root
WorkingDirectory={REMOTE_DIR}/backend
ExecStart={REMOTE_DIR}/backend/venv/bin/python ctrader_ingestion_daemon.py
Restart=always

[Install]
WantedBy=multi-user.target
"""

        tradier_service = f"""
[Unit]
Description=GEX Tradier Daemon
After=network.target

[Service]
User=root
WorkingDirectory={REMOTE_DIR}/backend
ExecStart={REMOTE_DIR}/backend/venv/bin/python tradier_ingestion_daemon.py
Restart=always

[Install]
WantedBy=multi-user.target
"""

        run_cmd(f"cat << 'EOF' > /etc/systemd/system/gex_api.service\n{fastapi_service}\nEOF")
        run_cmd(f"cat << 'EOF' > /etc/systemd/system/gex_ctrader.service\n{ctrader_service}\nEOF")
        run_cmd(f"cat << 'EOF' > /etc/systemd/system/gex_tradier.service\n{tradier_service}\nEOF")
        
        # 5. Reload systemd and start all
        run_cmd("systemctl daemon-reload")
        run_cmd("systemctl enable gex_api gex_ctrader gex_tradier")
        run_cmd("systemctl restart gex_api gex_ctrader gex_tradier")
        
        # 6. Setup Frontend via Nginx
        run_cmd("apt-get install -y nginx")
        nginx_conf = f"""
server {{
    listen 80;
    server_name _;
    
    root {REMOTE_DIR}/frontend/dist;
    index index.html;

    # API proxy
    location /api/ {{
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }}

    # WebSocket proxy
    location /ws/ {{
        proxy_pass http://127.0.0.1:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }}

    location / {{
        try_files $uri $uri/ /index.html;
    }}
}}
"""
        run_cmd(f"cat << 'EOF' > /etc/nginx/sites-available/default\n{nginx_conf}\nEOF")
        run_cmd("systemctl restart nginx")
        
        print(f"Deployment successful! Dashboard is live at http://{HOSTNAME}/")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
    finally:
        ssh.close()
        
if __name__ == "__main__":
        deploy()
