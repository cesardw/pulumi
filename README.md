# devops-lab

Infraestructura como código (IaC) con **Pulumi + Python** que despliega en **AWS** un servidor EC2 con **Docker**, donde corren dos contenedores backend detrás de un balanceador **Nginx**, más un panel de monitoreo con **Grafana**.

> Proyecto de aprendizaje DevOps: todo se crea, se modifica y se destruye con código, sin hacer clic en la consola de AWS.

---

## 📐 Arquitectura

```
                     Internet
                        │
            ┌───────────┴───────────┐
            │  Elastic IP (pública) │
            └───────────┬───────────┘
                        │
              ┌─────────▼─────────┐
              │ EC2 (Amazon Linux │
              │ 2023) + Docker    │
              │                   │
              │  :80  ┌─────────┐ │
              │ ─────►│ nginx-lb│ │
              │       └──┬───┬──┘ │
              │          │   │    │      /grafana/
              │   ┌──────▼┐ ┌▼──────┐    ┌────────┐
              │   │cumbre-│ │cumbre-│    │grafana │ :3000
              │   │  dev  │ │  qa   │    └────────┘
              │   └───────┘ └───────┘
              └───────────────────┘
                        ▲
                        │ pull de la imagen
                  ┌─────┴─────┐
                  │ Amazon ECR│  cumbre-web:latest
                  └───────────┘
```

**Cómo funciona, en simple:**

1. Pulumi crea la red (Security Group), los permisos (IAM) y el servidor EC2.
2. Al arrancar, el servidor ejecuta un script (*user data*) que instala Docker.
3. El script descarga la imagen `cumbre-web` desde ECR y levanta dos contenedores (`cumbre-dev` y `cumbre-qa`).
4. Nginx recibe el tráfico en el puerto 80 y lo reparte entre los dos backends (balanceo de carga).
5. Grafana corre en otro contenedor y guarda sus datos en un volumen de Docker.

---

## 🧰 Tecnologías

| Herramienta | Para qué se usa |
|---|---|
| [Pulumi](https://www.pulumi.com/) (Python) | Definir y crear la infraestructura como código |
| AWS EC2 | Servidor donde corren los contenedores |
| AWS ECR | Registro privado donde se guarda la imagen Docker |
| AWS IAM | Permisos del servidor (leer de ECR y acceso por SSM) |
| AWS SSM | Conectarse al servidor sin abrir el puerto SSH |
| Docker | Ejecutar los contenedores |
| Nginx | Balanceador de carga / proxy inverso |
| Grafana | Panel de monitoreo |

---

## 📁 Estructura del proyecto

```
.
├── __main__.py            # Programa principal de Pulumi (toda la infraestructura)
├── Pulumi.yaml            # Definición del proyecto (nombre y runtime)
├── Pulumi.<stack>.yaml    # Configuración de cada stack (dev, aws-dev, aws-prod)
├── nginx.conf             # Ejemplo de configuración de Nginx
└── requirements.txt       # Dependencias de Python
```

> La configuración real de Nginx se genera dentro de `__main__.py` y se escribe en el servidor en `/opt/nginx/nginx.conf`.

### Qué crea `__main__.py`

| Sección | Recursos |
|---|---|
| **Red** | Usa la VPC por defecto y crea un Security Group (puertos 80 y 3000 abiertos) |
| **IAM** | Rol + perfil de instancia con permisos de solo lectura a ECR y SSM |
| **User data** | Script que instala Docker, hace login en ECR y levanta todos los contenedores |
| **EC2** | Instancia Amazon Linux 2023, disco de 20 GB `gp3` cifrado, IMDSv2 obligatorio |
| **Elastic IP** | IP pública fija asociada al servidor |
| **Exports** | URLs, ID de la instancia y comando para conectarse por SSM |

---

## ✅ Requisitos previos

- Cuenta de AWS y [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configurado (`aws configure`)
- [Pulumi CLI](https://www.pulumi.com/docs/install/)
- Python 3.9 o superior
- Una imagen llamada `cumbre-web:latest` ya subida a tu repositorio de **Amazon ECR**
- (Opcional) [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) para conectarte al servidor

---

## 🚀 Cómo desplegarlo

```bash
# 1. Clonar el repositorio
git clone https://github.com/<tu-usuario>/<tu-repo>.git
cd <tu-repo>

# 2. Crear y activar el entorno virtual
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Iniciar sesión en Pulumi y seleccionar el stack
pulumi login
pulumi stack select aws-dev     # o: pulumi stack init aws-dev

# 5. Configurar la región (si el stack no la trae)
pulumi config set aws:region us-east-1

# 6. Ver qué se va a crear (sin cambiar nada)
pulumi preview

# 7. Crear la infraestructura
pulumi up
```

Al terminar, Pulumi muestra las salidas (*outputs*):

```
url_balanceador : http://<ip-publica>
url_grafana     : http://<ip-publica>:3000
instance_id     : i-xxxxxxxxxxxxxxxxx
ssm_connect     : aws ssm start-session --target i-xxxxxxxxxxxxxxxxx
aws_account_id  : 123456789012
```

> ⏱️ El servidor tarda unos minutos en instalar Docker y levantar los contenedores después de que `pulumi up` termina.

---

## ⚙️ Configuración

| Parámetro | Valor por defecto | Descripción |
|---|---|---|
| `devops-lab:instanceType` | `t3.micro` | Tipo de instancia EC2 |
| `devops-lab:az` | `us-east-1a` | Zona de disponibilidad |
| `aws:region` | — (obligatorio) | Región de AWS |

Ejemplo:

```bash
pulumi config set instanceType t3.small
pulumi config set az us-east-1b
```

### Stacks

Un *stack* es una instancia independiente del mismo proyecto (por ejemplo, un entorno).

| Stack | Uso |
|---|---|
| `aws-dev` | Desarrollo en AWS (con `allowedAccountIds` para evitar desplegar en una cuenta equivocada) |
| `aws-prod` | Producción en AWS |
| `dev` | Stack de pruebas (incluye un secreto cifrado `db_password`) |

---

## 🔍 Cómo probarlo

**Ver la aplicación balanceada:**

```bash
curl http://<ip-publica>
```

**Abrir Grafana:** entra a `http://<ip-publica>:3000` (o `http://<ip-publica>/grafana/`).
Usuario y contraseña iniciales: `admin` / `admin` (Grafana te pedirá cambiarla).

**Conectarte al servidor sin SSH:**

```bash
aws ssm start-session --target <instance_id>
```

**Ver los contenedores dentro del servidor:**

```bash
sudo docker ps
sudo docker logs nginx-lb
```

---

## 🧹 Destruir la infraestructura

Para no generar costos en AWS cuando termines:

```bash
pulumi destroy
```

---

## 🔒 Seguridad aplicada

- **Sin SSH:** el acceso al servidor es por AWS SSM, no hay puerto 22 abierto.
- **IMDSv2 obligatorio** en la instancia (`http_tokens="required"`).
- **Disco cifrado** (`encrypted=True`).
- **Permisos mínimos:** el servidor solo puede leer de ECR y usar SSM.
- **Rotación de logs de Docker** (3 archivos de 10 MB) para evitar llenar el disco.
- **Secretos cifrados** con Pulumi (`pulumi config set --secret`).

---

## 🛣️ Próximas mejoras

- [ ] Cerrar el puerto 3000 y exponer Grafana solo por `/grafana/`
- [ ] Cambiar la contraseña por defecto de Grafana y guardarla como secreto
- [ ] Usar etiquetas de imagen con versión en lugar de `latest`
- [ ] Añadir Prometheus y node-exporter para métricas
- [ ] Pipeline de CI/CD con GitHub Actions (`pulumi preview` en PR, `pulumi up` en `main`)
- [ ] Notificación a Slack al terminar el despliegue
- [ ] Mover a un Application Load Balancer + HTTPS (ACM)
- [ ] Migrar a ECS/Kubernetes

---

## 📚 Qué aprendí con este proyecto

- Infraestructura como código con Pulumi y Python
- Redes y seguridad básica en AWS (VPC, Security Groups, IAM)
- Contenedores con Docker y registro de imágenes con ECR
- Balanceo de carga con Nginx
- Automatización del arranque de un servidor con *user data*

---

## 📄 Licencia

Proyecto educativo. Añade aquí la licencia que prefieras (por ejemplo, MIT).
