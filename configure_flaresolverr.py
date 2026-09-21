import paramiko
import json

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.0.11', username='joanml', password='joanml', timeout=15)

def run_sudo(cmd):
    stdin, stdout, stderr = client.exec_command(f'echo joanml | sudo -S {cmd}')
    return stdout.read().decode('utf-8')

# Stop jackett
run_sudo('docker stop jackett')

cfg_path = '/home/joanml/media-stack/config/jackett/Jackett/ServerConfig.json'
stdin, stdout, stderr = client.exec_command(f'echo joanml | sudo -S cat {cfg_path}')
data = json.loads(stdout.read().decode('utf-8'))

data['FlareSolverrUrl'] = 'http://flaresolverr:8191'

sftp = client.open_sftp()
with sftp.file('/tmp/jackett_cfg.json', 'w') as f:
    json.dump(data, f, indent=2)
sftp.close()

run_sudo(f'cp /tmp/jackett_cfg.json {cfg_path}')
run_sudo(f'chown -R joanml:joanml /home/joanml/media-stack/config/jackett')
run_sudo('docker start jackett')

print("Jackett configurado con FlareSolverr: http://flaresolverr:8191")

client.close()
