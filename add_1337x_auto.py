import paramiko
import json

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.0.11', username='joanml', password='joanml', timeout=15)

script = """
import urllib.request
import json

radarr_key = "53ea9f5be1ca47da998fcfd8a2394288"
sonarr_key = "dd73a8f684104a48b018d33b23e0fefa"
jackett_key = "9ropgyn0hkj89jh83d0laljjzaac2xbi"

# 1. Fetch indexer schema template from Radarr
req = urllib.request.Request(f"http://127.0.0.1:7878/api/v3/indexer/schema?apiKey={radarr_key}")
with urllib.request.urlopen(req) as resp:
    schemas = json.loads(resp.read().decode('utf-8'))

torznab_schema = next((s for s in schemas if s['implementation'] == 'Torznab'), None)
if torznab_schema:
    torznab_schema['name'] = '1337x'
    torznab_schema['enableRss'] = True
    torznab_schema['enableAutomaticSearch'] = True
    torznab_schema['enableInteractiveSearch'] = True
    for f in torznab_schema['fields']:
        if f['name'] == 'baseUrl':
            f['value'] = 'http://192.168.0.11:9117/api/v2.0/indexers/1337x/results/torznab/'
        elif f['name'] == 'apiPath':
            f['value'] = '/api'
        elif f['name'] == 'apiKey':
            f['value'] = jackett_key
        elif f['name'] == 'categories':
            f['value'] = [2000, 2010, 2030, 2040, 2045, 2060, 2070, 100001, 100002, 100004, 100042, 100054, 100055, 100066, 100070, 100076]
    
    # POST to Radarr with forceSave
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:7878/api/v3/indexer?apiKey={radarr_key}&forceSave=true",
            data=json.dumps(torznab_schema).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            print("Radarr 1337x guardado exitosamente:", resp.status)
    except urllib.error.HTTPError as e:
        print("Error en Radarr:", e.code, e.read().decode('utf-8'))

# 2. Fetch schema template from Sonarr
req = urllib.request.Request(f"http://127.0.0.1:8989/api/v3/indexer/schema?apiKey={sonarr_key}")
with urllib.request.urlopen(req) as resp:
    s_schemas = json.loads(resp.read().decode('utf-8'))

s_torznab = next((s for s in s_schemas if s['implementation'] == 'Torznab'), None)
if s_torznab:
    s_torznab['name'] = '1337x'
    s_torznab['enableRss'] = True
    s_torznab['enableAutomaticSearch'] = True
    s_torznab['enableInteractiveSearch'] = True
    for f in s_torznab['fields']:
        if f['name'] == 'baseUrl':
            f['value'] = 'http://192.168.0.11:9117/api/v2.0/indexers/1337x/results/torznab/'
        elif f['name'] == 'apiPath':
            f['value'] = '/api'
        elif f['name'] == 'apiKey':
            f['value'] = jackett_key
        elif f['name'] == 'categories':
            f['value'] = [5000, 5030, 5040, 5070, 5080, 100005, 100006, 100041, 100071, 100074, 100075]
        elif f['name'] == 'animeCategories':
            f['value'] = [5070, 100028, 100078, 100079, 100080, 100081]
            
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:8989/api/v3/indexer?apiKey={sonarr_key}&forceSave=true",
            data=json.dumps(s_torznab).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            print("Sonarr 1337x guardado exitosamente:", resp.status)
    except urllib.error.HTTPError as e:
        print("Error en Sonarr:", e.code, e.read().decode('utf-8'))
"""

sftp = client.open_sftp()
with sftp.file('/tmp/add_1337x_auto.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = client.exec_command('python3 /tmp/add_1337x_auto.py')
print("STDOUT:\n", stdout.read().decode('utf-8'))
print("STDERR:\n", stderr.read().decode('utf-8'))

client.close()
