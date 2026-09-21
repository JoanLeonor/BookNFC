import paramiko
import json

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.0.11', username='joanml', password='joanml', timeout=15)

stdin, stdout, stderr = client.exec_command('curl -s "http://127.0.0.1:9117/api/v2.0/indexers/1337x/results?apikey=9ropgyn0hkj89jh83d0laljjzaac2xbi&Query=matrix"')
out = stdout.read().decode('utf-8')
try:
    data = json.loads(out)
    print("Resultados encontrados en 1337x:", len(data.get('Results', [])))
    if data.get('Results'):
        print("Primer resultado:", data['Results'][0].get('Title'), "| Categories:", data['Results'][0].get('CategoryDesc'), "| Category:", data['Results'][0].get('Category'))
    else:
        print("Sin resultados en 1337x:", out[:300])
except Exception as e:
    print("Error parseando respuesta de Jackett:", e, out[:300])

client.close()
