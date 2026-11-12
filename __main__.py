import os
import pulumi
import pulumi_docker as docker

# 1. Red de Docker compartida
red_devops = docker.Network("devops-network",
    name="devops-network",
    driver="bridge"
)

# 2. Imagen base local
mi_imagen = docker.RemoteImage("imagen-cumbre",
    name="cumbre-web:latest",
    keep_locally=True
)

# 3. Definimos las instancias que queremos desplegar
# Puedes agregar más elementos aquí si deseas escalar a 3, 4 o más contenedores.
instancias_backend = [
    {"name": "cumbre-dev", "port": 8082, "alias": "backend-1"},
    {"name": "cumbre-qa", "port": 8083, "alias": "backend-2"},
]

backend_aliases = []
contenedores = []

# 4. Bucle para crear los contenedores dinámicamente
for item in instancias_backend:
    contenedor = docker.Container(f"contenedor-{item['name']}",
        name=item['name'],
        image=mi_imagen.name,
        networks_advanced=[{
            "name": red_devops.name,
            "aliases": [item['alias']]
        }],
        ports=[{
            "internal": 8080,
            "external": item['port'],
        }]
    )
    contenedores.append(contenedor)
    backend_aliases.append(f"server {item['alias']}:8080;")

# 5. Generar automáticamente el archivo nginx.conf basado en las instancias activas
contenido_nginx = f"""events {{ worker_connections 1024; }}

http {{
    upstream mi_web_cluster {{
        {chr(10).join('        ' + a for a in backend_aliases)}
    }}

    server {{
        listen 80;

        location / {{
            proxy_pass http://mi_web_cluster;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }}
    }}
}}
"""

ruta_conf_local = os.path.abspath("nginx.conf")
with open(ruta_conf_local, "w") as f:
    f.write(contenido_nginx)

# 6. Contenedor del Balanceador (Nginx)
balanceador = docker.Container("load-balancer",
    name="nginx-lb",
    image="nginx:latest",
    networks_advanced=[{
        "name": red_devops.name
    }],
    ports=[{
        "internal": 80,
        "external": 8080,
    }],
    volumes=[{
        "container_path": "/etc/nginx/nginx.conf",
        "host_path": ruta_conf_local,
        "read_only": True,
    }]
)

# 7. Exportar URL principal
pulumi.export("url_balanceador", "http://localhost:8080")