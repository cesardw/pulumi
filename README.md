devops-lab

Infraestructura como código (IaC) con Pulumi + Python que aprovisiona en AWS una instancia EC2 (Amazon Linux 2023) con Docker, desplegando dos contenedores backend detrás de un balanceador de carga Nginx junto con un stack de observabilidad basado en Prometheus y Grafana.

Proyecto práctico de ingeniería DevOps: aprovisionamiento declarativo, configuración por entornos (stacks), principio de mínimo privilegio y acceso sin puertos SSH expuestos.

📐 Arquitectura

                         Internet
                            │
                ┌───────────┴───────────┐
                │  Elastic IP (pública) │
                └───────────┬───────────┘
                            │  TCP :80 (único puerto público)
                  ┌─────────▼──────────────────────────┐
                  │ EC2 (Amazon Linux 2023) + Docker   │
                  │ Red interna: devops-network        │
                  │                                    │
                  │        ┌──────────┐                │
                  │ ──────►│ nginx-lb │                │
                  │        └──┬───┬───┘                │
                  │     /     │   │  /grafana/         │
                  │    ┌──────▼┐ ┌▼──────┐             │
                  │    │cumbre-│ │cumbre-│             │
                  │    │  dev  │ │  qa   │             │
                  │    └───▲───┘ └───▲───┘             │
                  │        │ /metrics│                 │
                  │    ┌───┴─────────┴──┐  127.0.0.1   │
                  │    │   prometheus   │◄── :9090     │
                  │    └───────┬────────┘  (solo local)│
                  │            │ datasource            │
                  │            ▼                       │
                  │    ┌────────────────┐  :3000       │
                  │    │    grafana     │  (interno)   │
                  │    └────────────────┘              │
                  └────────────────────────────────────┘
                            ▲
                            │ docker pull (IAM Role)
                      ┌─────┴─────┐
                      │ Amazon ECR│  cumbre-web:<imageTag>
                      └───────────┘


Flujo de aprovisionamiento y ejecución

Red e IAM: Pulumi crea un Security Group que permite únicamente tráfico HTTP entrante (:80) y un rol IAM para leer imágenes de ECR y habilitar AWS Systems Manager (SSM).

Bootstrap (user_data): Al iniciar, la instancia EC2 instala Docker con rotación de logs configurada y crea la red bridge devops-network.

Contenedores de aplicación: Descarga cumbre-web desde Amazon ECR y levanta dos réplicas (cumbre-dev y cumbre-qa) con alias de red backend-1 y backend-2 en el puerto 8080.

Balanceo y proxy inverso: Nginx enruta las peticiones de / hacia el upstream de los backends y redirige /grafana/ hacia el contenedor de Grafana.

Observabilidad: Prometheus recolecta métricas cada 15 segundos desde /metrics en ambos backends y las almacena en un volumen persistente (prometheus-data), enlazado únicamente a 127.0.0.1:9090.

🧰 Stack Tecnológico

Componente

Tecnología

Función

IaC

Pulumi (Python)

Definición declarativa y gestión de estado por entorno

Cómputo y Red

AWS EC2 + Elastic IP + VPC

Instancia Amazon Linux 2023 con IP pública estática

Seguridad y Acceso

AWS IAM + SSM + IMDSv2

Autenticación sin llaves SSH ni credenciales estáticas

Registro

Amazon ECR

Almacenamiento privado de la imagen cumbre-web

Contenedores

Docker Engine

Ejecución aislada con volúmenes persistentes y rotación de logs

Proxy / LB

Nginx (1.27.2-alpine)

Balanceo de carga Round-Robin y enrutamiento de subpaths

Monitoreo

Prometheus (v2.55.1) + Grafana (11.3.0)

Recolección de métricas de aplicación y visualización

📁 Estructura del proyecto

.
├── __main__.py              # Definición de infraestructura AWS y script user_data
├── Pulumi.yaml              # Metadatos del proyecto y configuración de runtime Python
├── Pulumi.aws-dev.yaml      # Configuración del entorno de desarrollo en AWS
├── Pulumi.aws-prod.yaml     # Configuración del entorno de producción en AWS
├── Pulumi.dev.yaml          # Stack de pruebas con secretos cifrados
├── nginx.conf               # Plantilla base de referencia para Nginx
├── requirements.txt         # Dependencias de Python (pulumi, pulumi-aws)
└── README.md


Nota: Los archivos de configuración productivos (/opt/nginx/nginx.conf y /opt/prometheus/prometheus.yml) se generan dinámicamente desde __main__.py durante el arranque de la instancia. El archivo nginx.conf en la raíz sirve como referencia local.

✅ Requisitos previos

Cuenta de AWS con AWS CLI configurado (aws configure)

Pulumi CLI instalado

Python >= 3.10

Repositorio cumbre-web en Amazon ECR con la etiqueta configurada (ej. v1.0.0, latest, v1.2.0-dev), exponiendo el puerto 8080 y el endpoint /metrics

AWS Session Manager Plugin (para administración remota y túneles hacia Prometheus)

🚀 Despliegue

# 1. Clonar el repositorio
git clone https://github.com/cesardw/pulumi.git
cd pulumi

# 2. Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Seleccionar el stack deseado
pulumi login
pulumi stack select aws-dev

# 5. Previsualizar cambios
pulumi preview

# 6. Desplegar infraestructura
pulumi up


Salidas (Outputs) del despliegue

url_balanceador : http://<elastic-ip>
url_grafana     : http://<elastic-ip>/grafana/
instance_id     : i-xxxxxxxxxxxxxxxxx
ssm_connect     : aws ssm start-session --target i-xxxxxxxxxxxxxxxxx
aws_account_id  : 615299762808


⏱️ Tras finalizar pulumi up, la instancia toma entre 1 y 2 minutos adicionales para completar la instalación de Docker y descargar las imágenes desde ECR y Docker Hub.

⚙️ Configuración y Stacks

Todos los stacks comparten __main__.py y parametrizan versiones de imágenes y recursos mediante Pulumi.<stack>.yaml:

Variable

Valor por defecto

Descripción

aws:region

(obligatorio)

Región de AWS donde se despliega el stack

aws:allowedAccountIds

(opcional)

Lista blanca de cuentas AWS permitidas para evitar despliegues accidentales

devops-lab:instanceType

t3.micro

Tipo de instancia EC2

devops-lab:az

us-east-1a

Zona de disponibilidad

devops-lab:imageTag

v1.0.0

Etiqueta de la imagen cumbre-web en ECR

devops-lab:nginxTag

1.27.2-alpine

Versión de la imagen oficial de Nginx

devops-lab:prometheusTag

v2.55.1

Versión de la imagen oficial de Prometheus

devops-lab:grafanaTag

11.3.0

Versión de la imagen oficial de Grafana

Stacks configurados

aws-dev: Entorno de desarrollo en us-east-1 con bloqueo de cuenta (allowedAccountIds) y versiones actualizadas (grafanaTag: 11.4.0, prometheusTag: v3.0.0, nginxTag: 1.27.3-alpine, imageTag: latest).

aws-prod: Entorno de producción en us-east-1 (instanceType: t3.micro, imageTag: v1.2.0-dev).

dev: Entorno experimental que almacena secretos cifrados (db_password).

🔍 Verificación y Operación

1. Probar el balanceo de carga

curl -i http://<elastic-ip>


2. Acceder a Grafana

Abrir http://<elastic-ip>/grafana/ en el navegador.

Credenciales iniciales: admin / admin

Configurar Datasource de Prometheus: Connections → Data sources → Add data source → Prometheus con URL http://prometheus:9090.

3. Acceder a Prometheus de forma segura (Port Forwarding vía SSM)

Dado que el puerto 9090 solo escucha en 127.0.0.1 dentro de la instancia, utiliza un túnel SSM para consultarlo desde tu máquina local:

aws ssm start-session \
  --target <instance_id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["9090"],"localPortNumber":["9090"]}'


Luego abre http://localhost:9090/targets para confirmar que cumbre-backends (backend-1:8080 y backend-2:8080) estén en estado UP.

4. Inspeccionar contenedores en la instancia

aws ssm start-session --target <instance_id>
sudo docker ps
sudo docker logs -f nginx-lb


🔒 Seguridad implementada

Superficie mínima de ataque: Único puerto expuesto a Internet (80/TCP). Grafana se sirve bajo proxy inverso y Prometheus permanece aislado en localhost.

Zero-SSH: Administración remota exclusivamente mediante AWS SSM Session Manager; puerto 22 cerrado.

Endurecimiento de instancia: Metadatos EC2 restringidos a IMDSv2 (http_tokens="required") y volumen raíz gp3 de 20 GB cifrado en reposo.

Principio de mínimo privilegio: Perfil IAM limitado a lectura de ECR (AmazonEC2ContainerRegistryReadOnly) y agente SSM (AmazonSSMManagedInstanceCore).

Prevención de agotamiento de disco: Driver json-file de Docker limitado a 3 archivos rotativos de 10 MB cada uno.

Guardrails de cuenta: Uso de aws:allowedAccountIds para evitar aplicar cambios en cuentas AWS incorrectas.

🧹 Limpieza de recursos

Para eliminar toda la infraestructura y evitar cargos en AWS:

pulumi destroy --stack aws-dev


🛣️ Roadmap de mejoras

[ ] Automatizar el aprovisionamiento del datasource de Prometheus en Grafana mediante archivos de configuración (provisioning).

[ ] Inyectar la contraseña inicial de Grafana desde secretos cifrados de Pulumi (GF_SECURITY_ADMIN_PASSWORD).

[ ] Agregar node-exporter y cadvisor para métricas de host y contenedores.

[ ] Parametrizar los nombres de recursos con ${pulumi.get_stack()} para permitir la coexistencia simultánea de aws-dev y aws-prod en la misma cuenta.

[ ] Integrar un pipeline de CI/CD con GitHub Actions (pulumi preview en Pull Requests y pulumi up vía OIDC).

[ ] Implementar HTTPS mediante AWS Certificate Manager (ACM) y Application Load Balancer (ALB).

PROYECTO EDUCATIVO.///// CESAR DEVOPS///