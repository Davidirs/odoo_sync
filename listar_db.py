import xmlrpc.client

url = 'https://esmtcx.odoo.com'

# Nos conectamos al endpoint público 'db'
client = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/db')

try:
    # Pedimos la lista de bases de datos
    databases = client.list()
    print(f"Bases de datos disponibles en este servidor: {databases}")
except Exception as e:
    print(f"El servidor bloqueó la petición o hay un error: {e}")