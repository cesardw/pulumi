import json
import pulumi
import pulumi_aws as aws

# ==========================================
# 0. CONFIGURACIÓN
# ==========================================
config = pulumi.Config()
instance_type = config.get("instanceType") or "t3.micro"
az = config.get("az") or "us-east-1a"
image_tag = config.get("imageTag") or "v1.0.0"

# Versiones fijadas para evitar cambios inesperados al recrear recursos
grafana_tag = config.get("grafanaTag") or "11.3.0"
prometheus_tag = config.get("prometheusTag") or "v2.55.1"
nginx_tag = config.get("nginxTag") or "1.27.2-alpine"

identity = aws.get_caller_identity()
region = pulumi.Config("aws").require("region")

registry = f"{identity.account_id}.dkr.ecr.{region}.amazonaws.com"
imagen = f"{registry}/cumbre-web:{image_tag}"

instancias_backend = [
    {"name": "cumbre-dev", "alias": "backend-1"},
    {"name": "cumbre-qa", "alias": "backend-2"},
]

# ==========================================
# 1. RED: VPC POR DEFECTO + SECURITY GROUP
# ==========================================
vpc = aws.ec2.get_vpc(default=True)

subnets = aws.ec2.get_subnets(filters=[
    aws.ec2.GetSubnetsFilterArgs(name="vpc-id", values=[vpc.id]),
    aws.ec2.GetSubnetsFilterArgs(name="availability-zone", values=[az]),
])

sg = aws.ec2.SecurityGroup("web-sg",
    description="HTTP publico hacia el balanceador Nginx",
    vpc_id=vpc.id,
    ingress=[
    aws.ec2.SecurityGroupIngressArgs(
        protocol="tcp", from_port=80, to_port=80, cidr_blocks=["0.0.0.0/0"],
        description="HTTP",
    ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"],
    )],
    tags={"Name": "cumbre-web-sg"},
)

# ==========================================
# 2. IAM: LEER DE ECR + ACCESO POR SSM (sin SSH)/
# ==========================================
role = aws.iam.Role("ec2-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }),
)

attachments = [
    aws.iam.RolePolicyAttachment(f"ec2-role-policy-{i}", role=role.name, policy_arn=arn)
    for i, arn in enumerate([
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    ])
]

profile = aws.iam.InstanceProfile("ec2-profile", role=role.name)

# ==========================================
# 3. USER DATA: INSTALA DOCKER Y LEVANTA TODO
# ==========================================
upstream = "\n".join(f"        server {b['alias']}:8080;" for b in instancias_backend)
prometheus_targets = ", ".join(f"'{b['alias']}:8080'" for b in instancias_backend)

# Configuramos Nginx para rutear el tráfico de la app web y opcionalmente Grafana
nginx_conf = f"""events {{ worker_connections 1024; }}

http {{
    upstream mi_web_cluster {{
{upstream}
    }}

    server {{
        listen 80;

        location / {{
            proxy_pass http://mi_web_cluster;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }}

        # Opcional: Rutar Grafana a traves de la ruta /grafana/
                location /grafana/ {{
            proxy_pass http://grafana:3000;
            proxy_redirect http://localhost:3000/ http://$host/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}
    }}
}}
"""

prometheus_yml = f"""global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'cumbre-backends'
    metrics_path: /metrics
    static_configs:
      - targets: [{prometheus_targets}]
"""

# Rotación de logs de Docker (evita llenar el disco)
daemon_json = '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}'

run_backends = "\n".join(
    f"docker run -d --name {b['name']} --restart unless-stopped "
    f"--network devops-network --network-alias {b['alias']} {imagen}"
    for b in instancias_backend
)

# Comando para levantar Grafana persistiendo sus datos en un volumen local
run_grafana = """
docker run -d --name grafana --restart unless-stopped \\
  --network devops-network --network-alias grafana \\
  -e GF_SERVER_ROOT_URL='%(protocol)s://%(domain)s:%(http_port)s/grafana/' \\
  -e GF_SERVER_SERVE_FROM_SUB_PATH=true \\
  -v grafana-storage:/var/lib/grafana \\
  grafana/grafana-oss:latest
"""

# Comando para levantar Prometheus persistiendo sus datos en un volumen local
run_prometheus = """
docker run -d --name prometheus --restart unless-stopped \\
  --network devops-network --network-alias prometheus \\
  -p 127.0.0.1:9090:9090 \\
  -v /opt/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro \\
  -v prometheus-data:/prometheus \\
  prom/prometheus:latest
"""

user_data = f"""#!/bin/bash
set -euxo pipefail
export HOME=/root

dnf install -y docker
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{daemon_json}
JSON
systemctl enable --now docker

aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {registry}

docker network create devops-network

mkdir -p /opt/nginx
cat > /opt/nginx/nginx.conf <<'NGINX'
{nginx_conf}
NGINX

mkdir -p /opt/prometheus
cat > /opt/prometheus/prometheus.yml <<'PROMETHEUS'
{prometheus_yml}
PROMETHEUS

{run_backends}
{run_grafana}
{run_prometheus}

docker run -d --name nginx-lb --restart unless-stopped \\
  --network devops-network -p 80:80 \\
  -v /opt/nginx/nginx.conf:/etc/nginx/nginx.conf:ro nginx:latest
"""

# ==========================================
# 4. INSTANCIA EC2 (Amazon Linux 2023)
# ==========================================
ami = aws.ec2.get_ami(
    most_recent=True,
    owners=["amazon"],
    filters=[
        aws.ec2.GetAmiFilterArgs(name="name", values=["al2023-ami-2023.*-x86_64"]),
        aws.ec2.GetAmiFilterArgs(name="architecture", values=["x86_64"]),
    ],
)

server = aws.ec2.Instance("cumbre-server",
    ami=ami.id,
    instance_type=instance_type,
    subnet_id=subnets.ids[0],
    vpc_security_group_ids=[sg.id],
    iam_instance_profile=profile.name,
    associate_public_ip_address=True,
    user_data=user_data,
    user_data_replace_on_change=True,
    metadata_options=aws.ec2.InstanceMetadataOptionsArgs(
        http_endpoint="enabled", http_tokens="required",
    ),
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_size=20, volume_type="gp3", encrypted=True,
    ),
    tags={"Name": "cumbre-server"},
    opts=pulumi.ResourceOptions(depends_on=attachments),
)

eip = aws.ec2.Eip("cumbre-eip", instance=server.id, domain="vpc",
                  tags={"Name": "cumbre-eip"})

# ==========================================
# 5. EXPORTS
# ==========================================
pulumi.export("url_balanceador", eip.public_ip.apply(lambda ip: f"http://{ip}"))
pulumi.export("url_grafana", eip.public_ip.apply(lambda ip: f"http://{ip}/grafana/"))
pulumi.export("instance_id", server.id)
pulumi.export("ssm_connect", server.id.apply(lambda i: f"aws ssm start-session --target {i}"))
pulumi.export("aws_account_id", identity.account_id)