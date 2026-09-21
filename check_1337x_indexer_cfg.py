import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.0.11', username='joanml', password='joanml', timeout=15)

stdin, stdout, stderr = client.exec_command('echo joanml | sudo -S cat /home/joanml/media-stack/config/jackett/Jackett/Indexers/1337x.json 2>/dev/null || find /home/joanml/media-stack/config/jackett -name "1337x.json" -exec cat {} +')
print(stdout.read().decode('utf-8'))

client.close()
