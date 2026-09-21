import paramiko
import json

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.0.11', username='joanml', password='joanml', timeout=15)

stdin, stdout, stderr = client.exec_command('echo joanml | sudo -S cat /home/joanml/media-stack/config/jackett/Jackett/ServerConfig.json 2>/dev/null || find /home/joanml/media-stack/config/jackett -name "ServerConfig.json" -exec cat {} +')
print(stdout.read().decode('utf-8'))

client.close()
