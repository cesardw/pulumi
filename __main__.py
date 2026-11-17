import os
import pulumi
import pulumi_docker as docker

# ==========================================
# 1. RED DE DOCKER COMPARTIDA
# ==========================================

red_devops = docker.Network("devops-network",
    name="devops-network",
    driver="bridge"
)

# ==========================================
# 2. IMAGEN ALMACENADA EN AMAZON ECR
# ==========================================

mi_imagen = docker.RemoteImage("imagen-cumbre",
    name="615299762808.dkr.ecr.us-east-1.amazonaws.com/cumbre-web:latest",
    keep_locally=True
)

# ==========================================
# 3. INSTANCIAS DEL BACKEND
# ==========================================

instancias_backend = [
    {"name": "cumbre-dev", "port": 8082, "alias": "backend-1"},
    {"name": "cumbre-qa", "port": 8083, "alias": "backend-2"},
]

backend_aliases = []
contenedores = []

# ==========================================
# 4. CREACIÓN DINÁMICA DE CONTENEDORES
# ==========================================

for item in instancias_backend:

    contenedor = docker.Container(f"contenedor-{item['name']}",
        name=item['name'],

        # Utilizamos la imagen descargada desde ECR
        image=mi_imagen.image_id,

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

# ==========================================
# 5. GENERACIÓN AUTOMÁTICA DE NGINX.CONF
# ==========================================

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

# ==========================================
# 6. CONTENEDOR DEL BALANCEADOR NGINX
# ==========================================

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

# ==========================================
# 7. EXPORTAR URL PRINCIPAL
# ==========================================

pulumi.export("url_balanceador", "http://localhost:8080")

# ==========================================
# 8. VALIDACIÓN DE CONEXIÓN AWS
# ==========================================

import pulumi_aws as aws

identity = aws.get_caller_identity()

pulumi.export("aws_account_id", identity.account_id)
pulumi.export("aws_caller_arn", identity.arn)
pulumi.export("aws_user_id", identity.user_id)