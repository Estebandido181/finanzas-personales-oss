> Distribución OSS: para Gmail sigue primero [docs/GMAIL.md](../docs/GMAIL.md).
> Esta guía conserva comandos operativos de una instalación personal; no acredita
> verificación OAuth de Google ni aprobación para un servicio público compartido.
> Los tokens pueden caducar o revocarse; no se garantiza su duración indefinida.

# Guía de despliegue en Oracle Cloud

La reorganización conserva los entrypoints, `/app`, `frontend/dist` y las
rutas de datos/credenciales de esta guía. El esquema vigente sigue en la 0012;
no añade una migración nueva. Consulta [rutas y entrypoints](../docs/entrypoints.md)
para localizar las implementaciones internas. Los comandos de migración y
respaldo siguen siendo explícitos.

Esta guía instala Finanzas personales en una máquina virtual (VM) gratuita de
Oracle Cloud, con HTTPS en un subdominio gratuito de DuckDNS. Está pensada para
seguirla paso a paso, sin experiencia previa, copiando y pegando los comandos.

**Cómo leer los comandos**

- Los bloques que empiezan con `# En tu computador` se ejecutan en tu
  computador (Windows con PowerShell, macOS o Linux con la Terminal). Si
  creaste la llave SSH en **Cloud Shell** (paso 1.2, opción B), los comandos
  `ssh` y `scp` se ejecutan allí, y la llave es `~/.ssh/finanzas_vm` en lugar
  de `~/.ssh/oracle_finanzas`.
- Los bloques que empiezan con `# En la VM` se ejecutan dentro de la VM,
  después de conectarte por SSH (paso 1.4).
- Donde veas `tu-subdominio`, `tu-subdominio.duckdns.org` o `203.0.113.10`,
  pon tus propios datos. Son ejemplos inventados.
- `sudo` ejecuta un comando como administrador (root). En la VM no te pide
  contraseña.

**Antes de empezar: pegar en una terminal web**

Si trabajas desde el navegador (Cloud Shell de Oracle o una terminal web
parecida), pegar a veces falla:

- Si al pegar aparecen caracteres raros, como `^[[200~` al inicio o `~` al
  final del comando, ejecuta una vez esto en esa terminal y vuelve a pegar:

  ```bash
  bind 'set enable-bracketed-paste off'
  ```

  Solo vale para la sesión de bash donde lo ejecutas: hazlo en Cloud Shell y,
  si dentro de la VM pasa lo mismo, también allí (y otra vez cada vez que
  abras una sesión nueva). Para dejarlo fijo en esa máquina:

  ```bash
  echo 'set enable-bracketed-paste off' >> ~/.inputrc
  ```

  Se aplica desde la siguiente sesión que abras. Otra opción es escribir a
  mano los comandos cortos.
- Cuando tengas dudas, pega los comandos **de uno en uno** y mira el
  resultado de cada uno antes de seguir. En bloques largos, la terminal web a
  veces no ejecuta las últimas líneas.
- Donde la guía dice "escríbelo a mano", hazlo así: son comandos que piden
  una contraseña, y lo que pegues después se tomaría como la contraseña.

**Qué vas a tener al final**

```
Internet ──HTTPS (443)──► Caddy ──► 127.0.0.1:8000 (la app, usuario "finanzas")
          HTTP (80) ────► Caddy (solo redirige a HTTPS y renueva el certificado)
          SSH (22) ─────► solo con tu llave
```

| Qué | Dónde |
|---|---|
| Código de la app | `/opt/finanzas` (de root, solo lectura para la app) |
| Frontend nuevo compilado (`/app`) | `/opt/finanzas/frontend/dist`; Node, solo para compilarlo, en `/opt/node` |
| Base de datos y token de Gmail | `/var/lib/finanzas` (solo el usuario `finanzas`) |
| Respaldos diarios y previos a cada migración | `/var/backups/finanzas` (solo el usuario `finanzas`) |
| Secretos | `/etc/finanzas/finanzas.env` y `/etc/finanzas/duckdns.env` (solo root) |
| Servicios | `finanzas` (web), `caddy` (HTTPS), `finanzas-migrar` (solo al instalar o actualizar) |
| Temporizadores | `finanzas-sync` (cada 6 h), `finanzas-respaldo` (diario), `duckdns` (cada 30 min) |

Todo es gratuito: Oracle Always Free, DuckDNS, Let's Encrypt (lo usa Caddy) y
Caddy.

---

## 1. Crear la cuenta y la VM Always Free

### 1.1 Cuenta de Oracle Cloud

1. Entra a <https://www.oracle.com/cloud/free/> y pulsa "Start for free".
2. Elige tu **región de origen** (home region) con cuidado: los recursos Always
   Free solo se crean en ella y no se puede cambiar después. Una cercana, por
   ejemplo "Colombia Central (Bogotá)", "Brazil East (Sao Paulo)" o
   "US East (Ashburn)".
3. Oracle pide una tarjeta para verificar la identidad. Mientras no pases la
   cuenta a "Pay As You Go", **no cobra nada**: solo deja crear recursos
   marcados como "Always Free".

### 1.2 Crear tu llave SSH

La llave SSH es como una llave física: la parte privada se queda donde la
creas y la pública se instala en la VM. Así entras sin contraseña. Elige
**una** de estas dos opciones.

**Opción A: en tu computador de casa (propio).**

```bash
# En tu computador (PowerShell, macOS o Linux)
ssh-keygen -t ed25519 -f ~/.ssh/oracle_finanzas -C "finanzas-vm"
```

Te pide una frase de paso (passphrase): pon una y recuérdala; protege la llave
si alguien copia el archivo. Se crean dos archivos:

- `~/.ssh/oracle_finanzas`: **privada**. Nunca la compartas ni la subas a ningún lado.
- `~/.ssh/oracle_finanzas.pub`: pública. Es la que se pega en Oracle.

Para ver la pública y copiarla: `cat ~/.ssh/oracle_finanzas.pub`.

**Opción B: desde Cloud Shell (recomendada en un computador compartido).**

Cloud Shell es una terminal que Oracle te da en el navegador. Se abre con el
ícono `>_` de la parte de arriba de la consola de Oracle. Si trabajas desde un
computador que no es tuyo (por ejemplo, el de la universidad), es la opción
recomendada: la llave privada se crea y se queda en Cloud Shell y **nunca toca
ese computador**.

Cloud Shell funciona en **modo FIPS**, que no permite llaves `ed25519` (sale
el error "ED25519 keys are not allowed in FIPS mode"). Allí se usa RSA de
4096 bits:

```bash
# En Cloud Shell
ssh-keygen -t rsa -b 4096 -f ~/.ssh/finanzas_vm -C "vm-finanzas"
cat ~/.ssh/finanzas_vm.pub
```

- La llave queda en el directorio personal (home) de Cloud Shell, que se
  conserva entre sesiones. **No la borres**: sin ella no puedes entrar a la VM.
- **Ojo:** Oracle borra el home de Cloud Shell si pasas unos **6 meses** sin
  usarlo, y con él la llave `~/.ssh/finanzas_vm`. Para no quedarte fuera,
  crea pronto una segunda llave de respaldo en tu computador de casa y
  añádela a `~/.ssh/authorized_keys` de la VM (ver "Añadir una segunda llave",
  justo abajo), o abre Cloud Shell de vez en cuando.
- **Añadir una segunda llave.** Más adelante puedes
  añadir una segunda llave desde tu computador de casa:
  créala con la opción A, entra a la VM desde Cloud Shell y añade la línea de
  `oracle_finanzas.pub` al final de `~/.ssh/authorized_keys` de la VM (con
  `nano ~/.ssh/authorized_keys`, en una línea nueva, sin tocar las demás).

### 1.3 Crear la VM

En la consola de Oracle (<https://cloud.oracle.com>): menú ☰ → **Compute** →
**Instances** → **Create instance**. Los nombres de los botones pueden variar un
poco; busca siempre la etiqueta **"Always Free-eligible"**.

1. **Name:** `finanzas`.
2. **Image and shape** → **Edit**:
   - **Image:** "Change image" → **Canonical Ubuntu** → **24.04** (no la
     "Minimal"). Debe decir "Always Free-eligible".
   - **Shape:** "Change shape". Cualquiera de estas dos es gratuita:
     - **Ampere** → `VM.Standard.A1.Flex` con 1 OCPU y 6 GB de memoria
       (recomendada; hay más memoria).
     - **Specialty and previous generation** → `VM.Standard.E2.1.Micro`
       (1 GB de memoria; alcanza para esta app).
   - Si al crear sale **"Out of capacity"** con Ampere, intenta más tarde, en
     otro "Availability domain" o usa la E2.1.Micro.
3. **Networking:** deja "Create new virtual cloud network" y "Create new public
   subnet", con **"Assign a public IPv4 address"** activado.
   - En la consola nueva el interruptor se llama **"Automatically assign
     public IPv4 address"** y puede venir **apagado**: actívalo. Sin él la VM
     no tiene IP pública y no podrás conectarte.
   - Si sale un aviso sobre IPv6, puedes ignorarlo: esta guía solo usa IPv4.
4. **Add SSH keys:** elige **"Paste public keys"** y pega la llave pública del
   paso 1.2 (`oracle_finanzas.pub` o `finanzas_vm.pub`).
   - En un computador compartido **no** uses "Generate a key pair for me":
     descarga la llave privada a ese computador.
   - La llave debe quedar en **una sola línea**, empezar por `ssh-rsa ` o
     `ssh-ed25519 ` (con un **espacio** después del tipo) y terminar en el
     comentario (`vm-finanzas` o `finanzas-vm`). Al copiarla desde la terminal
     es común que se pierda ese espacio o que se cuelen saltos de línea; si
     pasa, Oracle la rechaza o no podrás entrar. Revísala antes de seguir.
5. **Boot volume:** deja el tamaño por defecto (hasta 200 GB en total son gratis).
6. Pulsa **Create** y espera a que el estado diga **Running**. Anota la
   **Public IP address** (por ejemplo `203.0.113.10`).

### 1.4 Conectarte por SSH

El usuario de las imágenes Ubuntu de Oracle es `ubuntu`. Conéctate desde donde
creaste la llave, con la ruta de esa llave:

```bash
# En tu computador (opción A)
ssh -i ~/.ssh/oracle_finanzas ubuntu@203.0.113.10
```

```bash
# En Cloud Shell (opción B)
ssh -i ~/.ssh/finanzas_vm ubuntu@203.0.113.10
```

La primera vez pregunta si confías en el servidor: escribe `yes`. Para salir
de la VM: `exit`.

> Opcional, para no escribir la ruta de la llave cada vez: añade esto a
> `~/.ssh/config` (en tu computador o en Cloud Shell, donde esté la llave) y
> luego entra con `ssh finanzas`. En Cloud Shell, pon
> `IdentityFile ~/.ssh/finanzas_vm`.
>
> ```
> Host finanzas
>     HostName 203.0.113.10
>     User ubuntu
>     IdentityFile ~/.ssh/oracle_finanzas
> ```

---

## 2. Reservar la IP pública

La IP que Oracle asigna al crear la VM es "efímera": puede cambiar si la VM se
detiene del todo. Una IP **reservada** se queda contigo. (Aunque cambiara, el
temporizador de DuckDNS del paso 10 actualizaría el subdominio solo, pero con
la reservada evitas cortes.)

En la consola: **Compute** → **Instances** → `finanzas` → pestaña **Networking**
(o "Attached VNICs") → la VNIC → **IP administration** / **IPv4 Addresses**.

En la consola actual, la opción **"Reserved public IP"** solo aparece cuando la
IP privada **no tiene** IP pública. Por eso se hace en dos pasadas:

1. **Primera pasada: quitar la IP efímera.** En la IP privada principal, menú
   ⋮ → **Edit** → en "Public IP type" elige **No public IP** → **Update**.
   La sesión SSH que tengas abierta se corta: es normal, la VM se quedó sin IP
   pública por un momento.
2. **Segunda pasada: poner la reservada.** Vuelve a ⋮ → **Edit** → elige
   **Reserved public IP** y, o bien **Create new reserved IP address** (dale
   un nombre, por ejemplo `finanzas-ip`), o bien **Select existing** si ya la
   habías creado → **Update**.

Alternativa: crear antes la IP reservada en **Networking** → **IP management**
→ **Reserved public IPs** → **Reserve public IP address**, y en la segunda
pasada elegirla con "Select existing".

**La IP cambia.** La reservada casi nunca es la misma que tenías. Anota la
nueva, reconéctate con ella (`ssh -i ... ubuntu@203.0.113.20`, por ejemplo) y,
como para SSH es un servidor "nuevo", vuelve a preguntar si confías en él:
responde `yes`. Si ya tenías el bloque `Host finanzas` del paso 1.4, cambia
allí `HostName`. Desde ahora usa siempre esta IP.

> **Costos: pon una alerta.** Si pasaste la cuenta a **Pay As You Go**, Oracle
> **sí puede cobrar** por lo que salga de Always Free. Para enterarte a tiempo:
>
> 1. En la consola: menú ☰ → **Billing & Cost Management** → **Budgets** →
>    **Create Budget**.
> 2. Monto: **USD 1 al mes**. Añade una regla de alerta al **1 %** del
>    presupuesto con tu correo. Ese 1 % (un centavo de dólar) es a propósito:
>    lo normal es que el gasto sea cero, así que la alerta avisa ante
>    **cualquier** cargo, por pequeño que sea.
> 3. Al día siguiente de crear la VM y la IP reservada, revisa
>    **Billing & Cost Management** → **Cost Analysis**. Si aparece algún
>    cargo (por ejemplo, por la IP reservada o el disco), revisa qué recurso
>    es antes de seguir.
>
> Con la cuenta gratuita, sin Pay As You Go, Oracle no deja crear recursos de
> pago, pero la alerta tampoco sobra.

---

## 3. DuckDNS: el subdominio

1. Entra a <https://www.duckdns.org> e inicia sesión (con GitHub, Google, etc.).
2. Arriba verás tu **token**: una cadena con forma
   `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`. Es una contraseña: no la compartas.
   La usarás en el paso 7.
3. En "sub domain" escribe el nombre que quieras (por ejemplo `tu-subdominio`)
   y pulsa **add domain**. Tu dirección será `tu-subdominio.duckdns.org`.
4. En la fila del subdominio, en "current ip", escribe la IP reservada del
   paso 2 y pulsa **update ip**.

Comprueba desde tu computador que ya apunta a la VM (puede tardar unos minutos):

```bash
# En tu computador
nslookup tu-subdominio.duckdns.org
```

---

## 4. Red: abrir solo los puertos 80 y 443

Hay **dos** cortafuegos y hay que abrir los puertos en los dos: el de la red de
Oracle (Security List) y el de la propia VM (`iptables`).

### 4.1 Security List de la red de Oracle

En la consola: **Networking** → **Virtual cloud networks** → tu VCN → pestaña
**Security** (o "Security Lists") → **Default Security List for ...** →
**Security rules** → **Add Ingress Rules**. Añade dos reglas:

| Source CIDR | IP Protocol | Destination Port Range |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

Deja "Stateless" **sin marcar**. La regla del puerto 22 (SSH) ya viene creada;
no añadas ninguna otra. (Si en vez de Security List tu VM usa un Network
Security Group, NSG, añade las mismas reglas allí.)

### 4.2 iptables dentro de la VM

Las imágenes Ubuntu de Oracle traen reglas de `iptables` que rechazan todo lo
que no sea SSH, con una regla `REJECT` al final. Hay que insertar las reglas de
80 y 443 **antes** de ese REJECT (si se añaden después, nunca se aplican).

**No uses `ufw`** a la vez (pelearía con estas reglas) y **nunca borres todas
las reglas** (`iptables -F`): Oracle usa algunas para que la VM arranque.

```bash
# En la VM: ver las reglas actuales con su número
sudo iptables -L INPUT --line-numbers -n
```

Verás algo así; lo importante es el número de la línea `REJECT`:

```
num  target  prot opt source     destination
1    ACCEPT  all  --  0.0.0.0/0  0.0.0.0/0   state RELATED,ESTABLISHED
2    ACCEPT  icmp --  0.0.0.0/0  0.0.0.0/0
3    ACCEPT  all  --  0.0.0.0/0  0.0.0.0/0
4    ACCEPT  udp  --  0.0.0.0/0  0.0.0.0/0   udp spt:123
5    ACCEPT  tcp  --  0.0.0.0/0  0.0.0.0/0   state NEW tcp dpt:22
6    REJECT  all  --  0.0.0.0/0  0.0.0.0/0   reject-with icmp-host-prohibited
```

Estos comandos buscan el número del REJECT e insertan las dos reglas justo
antes, y luego las guardan para que sobrevivan a un reinicio:

```bash
# En la VM
N=$(sudo iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')
echo "El REJECT está en la línea: $N"
sudo iptables -I INPUT "$N" -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT "$N" -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save
sudo iptables -L INPUT --line-numbers -n
```

Al final, las reglas `dpt:80` y `dpt:443` deben aparecer **antes** del
`REJECT`. Si `echo` mostró una línea vacía, no hay REJECT en tu imagen: en ese
caso usa `sudo iptables -A INPUT ...` en lugar de `-I INPUT "$N"`.
`netfilter-persistent save` guarda las reglas en `/etc/iptables/rules.v4`.

> **Si las reglas quedaron después del REJECT** (por ejemplo, porque usaste
> `-A` teniendo un REJECT, o las pegaste dos veces), corrígelo así:
>
> 1. Lista las reglas con `sudo iptables -L INPUT --line-numbers -n` y anota
>    los números de **todas** las líneas `dpt:80` y `dpt:443`, estén antes o
>    después del `REJECT`. (Si las pegaste dos veces, hay copias repetidas
>    antes del REJECT; si solo borraras las de después, el paso 3 añadiría
>    otra copia más.)
> 2. Bórralas todas **empezando por el número más alto**, una por una. Al
>    borrar una regla, las de abajo suben un número; si empiezas por la más
>    alta, los números que anotaste siguen valiendo. Por ejemplo, si están en
>    la 6, la 7, la 9 y la 10:
>
>    ```bash
>    # En la VM
>    sudo iptables -D INPUT 10
>    sudo iptables -D INPUT 9
>    sudo iptables -D INPUT 7
>    sudo iptables -D INPUT 6
>    ```
>
>    Lista otra vez y comprueba que ya no queda ninguna `dpt:80` ni `dpt:443`.
> 3. Vuelve a ejecutar el bloque de arriba (el que calcula `N` con `awk`)
>    **una sola vez**: así las inserta con el número **actual** del REJECT.
>    Ese bloque ya hace `netfilter-persistent save` y vuelve a listar;
>    comprueba que `dpt:80` y `dpt:443` aparecen **antes** del `REJECT` y una
>    sola vez cada una.

---

## 5. Preparar la VM

> **Atajo para una VM nueva: `deploy/preparar-servidor.sh`.** Hace los pasos
> 4.2 a 10 en un solo comando y se puede repetir sin romper nada: cada paso
> mira si ya está hecho. No pone los secretos (paso 7) ni autoriza Gmail
> (paso 8), no migra la base (si no está al día, lo dice y se despliega con
> `desplegar.sh --permitir-migraciones`), no arranca la app sin base, y no
> activa **DuckDNS** ni la **sincronización con Gmail** salvo que lo pidas
> con `--produccion` (en el cambio de VM): dos VM se pelearían el subdominio
> y dos sincronizaciones dejarían dos bases distintas. Con `--commit <sha>` clona el mismo
> commit que corre la VM anterior, para que su base encaje sin migrar. Si falta
> registrar la llave de despliegue en GitHub, la muestra y se detiene: la
> registras y lo vuelves a correr. Al final lista lo que quedó pendiente.
>
> Con Terraform, cloud-init lo deja en la VM y lo corre al crearla. A mano, como
> el repositorio es privado, cópialo desde tu computador y córrelo:
>
> ```bash
> # En tu computador
> scp deploy/preparar-servidor.sh ubuntu@203.0.113.20:~/
> # En la VM nueva
> sudo bash ~/preparar-servidor.sh --dominio tu-subdominio.duckdns.org
> ```
>
> Las secciones de abajo explican cada paso, por si prefieres hacerlo a mano
> o necesitas entender qué hace el script.

### 5.1 Actualizaciones y zona horaria

```bash
# En la VM
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y unattended-upgrades git python3-venv sqlite3 curl
sudo dpkg-reconfigure -plow unattended-upgrades   # responde "Yes"
sudo timedatectl set-timezone America/Bogota
sudo reboot
```

- `unattended-upgrades` instala solas las actualizaciones de seguridad.
- La zona horaria de Colombia hace que los temporizadores y los nombres de los
  respaldos usen tu hora. (La app ya calcula siempre en hora de Colombia.)
- `reboot` reinicia la VM; espera un minuto y vuelve a conectarte.
- **No** ejecutes `do-release-upgrade` aunque, al entrar, Ubuntu anuncie una
  versión nueva. El servidor se queda en Ubuntu 24.04 (decisión D13 de la
  especificación); las actualizaciones de seguridad siguen llegando igual.

Si `dpkg-reconfigure -plow unattended-upgrades` no mostró ninguna pregunta,
comprueba que las actualizaciones automáticas quedaron activas:

```bash
# En la VM
cat /etc/apt/apt.conf.d/20auto-upgrades
```

Debe mostrar estas dos líneas, las dos con `"1"`:

```
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
```

Si el archivo no existe o alguna tiene `"0"`, escríbelo así:

```bash
# En la VM
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
    | sudo tee /etc/apt/apt.conf.d/20auto-upgrades
```

> Opcional: para que la VM se reinicie sola de madrugada cuando una
> actualización lo pida, en `/etc/apt/apt.conf.d/50unattended-upgrades` quita
> el `//` de `Unattended-Upgrade::Automatic-Reboot "false";`, cámbialo a
> `"true"` y fija `Unattended-Upgrade::Automatic-Reboot-Time "04:00";`.

### 5.2 Usuario del sistema y carpetas

La app corre con un usuario propio, `finanzas`, que no tiene contraseña, ni
shell, ni forma de iniciar sesión. Si alguien encontrara un fallo en la app,
solo podría tocar lo de ese usuario.

```bash
# En la VM
sudo useradd --system --user-group --home-dir /var/lib/finanzas \
    --no-create-home --shell /usr/sbin/nologin finanzas
sudo passwd -l finanzas

# Datos (base y token de Gmail) y respaldos: solo el usuario finanzas (0700).
sudo install -d -o finanzas -g finanzas -m 0700 \
    /var/lib/finanzas /var/lib/finanzas/gmail /var/backups/finanzas

# Secretos: solo root (0700). systemd los lee como root al arrancar cada
# servicio y se los pasa; la app nunca necesita abrir /etc/finanzas.
sudo install -d -o root -g root -m 0700 /etc/finanzas
```

`/opt/finanzas` (el código) lo crea `git clone` en el paso 6, de root y de solo
lectura para la app: así la app no puede modificar su propio código.

> Opcional, solo con la E2.1.Micro (1 GB de memoria): un archivo de
> intercambio de 1 GB evita quedarse sin memoria al instalar.
>
> ```bash
> sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
> sudo mkswap /swapfile && sudo swapon /swapfile
> echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
> ```

### 5.3 Apagar `rpcbind`

Las imágenes Ubuntu de Oracle traen `rpcbind` (un servicio para compartir
discos en red, NFS) escuchando en el puerto 111. La app no lo necesita, y
todo lo que escucha hacia fuera es algo más que proteger; `verificar.sh`
(paso 12) lo marcaría como puerto sobrante.

```bash
# En la VM
sudo systemctl disable --now rpcbind.socket rpcbind.service
```

Si sale un aviso como "Stopping 'rpcbind.service', but its triggering units
are still active", es normal: el mismo comando apaga también `rpcbind.socket`,
que es la unidad que lo volvía a arrancar.

Opcional, para que ningún otro paquete lo vuelva a encender:

```bash
# En la VM
sudo systemctl mask rpcbind.socket rpcbind.service
```

Comprueba que el puerto 111 ya no aparece: `sudo ss -ltnp | grep ':111 '` no
debe mostrar nada.

---

## 6. Instalar la app

Se instala siempre la rama `main` (la versión estable).

> **Probar antes de la entrega.** Si quieres probar `develop` en la VM antes de
> que pase a `main`, clona con `--branch develop` en lugar de `--branch main`
> en los comandos de abajo. Cuando el dueño haga el merge a `main`, pasa la VM
> a `main`:
>
> ```bash
> # En la VM
> sudo git -C /opt/finanzas fetch origin main && sudo git -C /opt/finanzas checkout main
> ```
>
> Y a continuación sigue el procedimiento completo del paso 13.2 (respaldo,
> reinstalar los requisitos, copiar las unidades de systemd, `daemon-reload`,
> migrar la base, revisar el Caddyfile, arrancar `finanzas` y ejecutar
> `verificar.sh`): entre `develop` y `main` pueden haber cambiado más cosas
> que el código.

**Si el repositorio es público:**

```bash
# En la VM
sudo git clone --branch main https://github.com/Estebandido181/finanzas-personales-oss.git /opt/finanzas
```

**Si el repositorio es privado**, crea una "deploy key" de **solo lectura**
(sirve solo para este repositorio y no puede escribir en él):

```bash
# En la VM
sudo ssh-keygen -t ed25519 -f /root/.ssh/finanzas_deploy -N "" -C "finanzas-vm-deploy"
sudo cat /root/.ssh/finanzas_deploy.pub
```

En GitHub: el repositorio → **Settings** → **Deploy keys** → **Add deploy key**,
pega esa línea y deja **sin marcar** "Allow write access". Luego:

```bash
# En la VM
sudo GIT_SSH_COMMAND="ssh -i /root/.ssh/finanzas_deploy" \
    git clone --branch main git@github.com:Estebandido181/finanzas-personales-oss.git /opt/finanzas
sudo git -C /opt/finanzas config core.sshCommand "ssh -i /root/.ssh/finanzas_deploy"
```

La primera vez, `ssh` pregunta si confías en `github.com` y muestra su huella
(fingerprint). Antes de escribir `yes`, comprueba que la huella ED25519 es
exactamente esta:

```
SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU
```

Es la que publica GitHub en
<https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints>
(si no coincide con esa página, no sigas: no estarías hablando con GitHub).

**En los dos casos**, crea el entorno virtual e instala las dependencias y el paquete local. Así los comandos `python -m finanzas.*` siguen disponibles desde `/opt/finanzas` para systemd:

```bash
# En la VM
sudo python3 -m venv /opt/finanzas/.venv
sudo /opt/finanzas/.venv/bin/pip install --upgrade pip
sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/backend/requirements.txt -e /opt/finanzas
```

Para comprobar que la instalación quedó bien, importa la app **desde
`/opt/finanzas`**:

```bash
# En la VM
cd /opt/finanzas
.venv/bin/python -c "import finanzas.web.app; print('La app se importa bien.')"
cd ~
```

La app no se instala como paquete de Python: se importa desde la carpeta del
código. Por eso los servicios usan `WorkingDirectory=/opt/finanzas`, y por eso
esta prueba, hecha desde otra carpeta, daría `ModuleNotFoundError: No module
named 'finanzas'` aunque todo esté bien.

### 6.1 Node y el frontend nuevo (`/app`)

Desde la v2 la app tiene un frontend hecho con React en `/app`. Desde el ítem 20
es la **única interfaz** (la v1 se retiró y `/` redirige a `/app/`).
El navegador no lo puede usar tal cual: hay que **compilarlo** a archivos
estáticos (`/opt/finanzas/frontend/dist`), que después sirve la misma app en
`https://tu-subdominio.duckdns.org/app/`. Para compilar se usa **Node**, y solo
para eso: Node no queda corriendo ni abre ningún puerto.

Se instala una versión **fija** de Node (24.21.0), descargada de nodejs.org, y
antes de instalarla se comprueba su huella SHA-256. Así, si el archivo llegara
alterado, el comando falla y no se instala nada. Ubuntu trae una versión de
Node demasiado vieja, por eso no se usa `apt`.

Pega los comandos de uno en uno. Los de abajo son para la VM **Ampere
(arm64)**, la recomendada en el paso 1.3:

```bash
# En la VM
cd /tmp && curl -fsSLO https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-arm64.tar.xz
echo "6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2  node-v24.21.0-linux-arm64.tar.xz" | sha256sum -c -
sudo mkdir -p /opt/node && sudo tar -xJf node-v24.21.0-linux-arm64.tar.xz -C /opt/node --strip-components=1 --no-same-owner
rm /tmp/node-v24.21.0-linux-arm64.tar.xz && cd ~
/opt/node/bin/node --version
```

El segundo comando debe decir `node-v24.21.0-linux-arm64.tar.xz: OK`. Si dice
`FAILED`, **no sigas**: borra el archivo y vuelve a descargarlo. El último
debe mostrar `v24.21.0`.

> **Si tu VM es la E2.1.Micro (x86, 1 GB)**, cambia `arm64` por `x64` en los
> comandos primero, tercero y cuarto, y usa este segundo comando en lugar del
> de arriba. Con 1 GB de memoria, crea antes el archivo de intercambio del
> paso 5.2.
>
> ```bash
> # En la VM (solo E2.1.Micro)
> echo "fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6  node-v24.21.0-linux-x64.tar.xz" | sha256sum -c -
> ```

Ahora compila el frontend. `npm ci` instala exactamente las versiones del
archivo `frontend/package-lock.json`; `--ignore-scripts` evita que se ejecute
código de esas librerías al instalarlas (ninguna lo necesita). `npm run build`
comprueba los tipos y deja el resultado en `frontend/dist`:

```bash
# En la VM
cd /opt/finanzas/frontend && sudo env PATH=/opt/node/bin:/usr/bin:/bin npm ci --ignore-scripts
sudo env PATH=/opt/node/bin:/usr/bin:/bin npm run build && cd ~
```

Termina con una línea `✓ built in …`. Ocupa unos 220 MB en
`frontend/node_modules` (librerías para compilar) y Node otros 200 MB en
`/opt/node`. **Sin `frontend/dist` la app no abre**: arranca y la API
(`/api`) responde, pero `/app` da 503 "El frontend nuevo no está compilado…" y
ya no hay una interfaz v1 de respaldo.

---

## 7. Secretos

Los secretos viven **solo** en la VM, en `/etc/finanzas`. Nunca en el
repositorio, ni en un correo, ni en un chat.

### 7.1 `/etc/finanzas/finanzas.env` (root, 0600)

Se hace en tres partes: primero se genera el hash de tu contraseña, luego se
escribe el archivo y al final se comprueba. Los secretos pasan por variables
de la shell y nunca se muestran en pantalla.

Van separadas a propósito: el comando que pide la contraseña lee lo que
escribes en la terminal, así que, si pegaras todo junto, las líneas pegadas
después se tomarían como la contraseña. Además, en la terminal web, las
últimas líneas de un bloque largo a veces no se ejecutan.

**Parte A: escríbela a mano, línea por línea.** Te pide la contraseña de la
app dos veces (mínimo 12 caracteres; no se ve al escribirla).

```bash
# En la VM (parte A: a mano)
cd /opt/finanzas
HASH=$(.venv/bin/python -m finanzas.seguridad)
echo "${HASH:0:7}"
```

La última línea muestra solo el comienzo del hash, que debe ser `scrypt:`. Si
muestra una línea vacía (las contraseñas no coincidían o eran muy cortas),
vuelve a escribir la línea `HASH=...` antes de seguir.

**Parte B: esta sí se puede pegar.** Genera la clave de sesión y escribe el
archivo. Si no hay un hash válido (la parte A falló), no escribe nada: dice
"ERROR" y basta con repetir la parte A y luego esta.

```bash
# En la VM (parte B: se puede pegar)
if [[ $HASH == scrypt:* ]]; then
SECRETO=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
sudo install -o root -g root -m 0600 /dev/null /etc/finanzas/finanzas.env
sudo tee /etc/finanzas/finanzas.env > /dev/null <<EOF
APP_PASSWORD_HASH=$HASH
SESSION_SECRET=$SECRETO
COOKIE_SECURE=true
DB_PATH=/var/lib/finanzas/finanzas.db
GMAIL_TOKEN=/var/lib/finanzas/gmail/token.json
EOF
echo "finanzas.env escrito."
else
echo "ERROR: no se generó el hash; no se escribió nada. Repite la parte A."
fi
```

**Parte C: a mano.** Borra las variables con los secretos y comprueba el
archivo sin mostrar su contenido.

```bash
# En la VM (parte C: a mano)
unset HASH SECRETO
cd ~
sudo stat -c '%U:%G %a %n' /etc/finanzas/finanzas.env
sudo grep -c = /etc/finanzas/finanzas.env
sudo grep -c '^APP_PASSWORD_HASH=scrypt:' /etc/finanzas/finanzas.env
```

Debe mostrar, en este orden:

- `root:root 600 /etc/finanzas/finanzas.env`;
- `5` (las cinco variables);
- `1` (una sola línea `APP_PASSWORD_HASH` y con un hash válido).

`grep -c` solo cuenta líneas, no las muestra. **Nunca** revises este archivo
con `cat`: dejaría los secretos en la pantalla. El archivo es solo de root
porque quien lo lee es systemd (como root) al arrancar los servicios; la app
recibe las variables ya cargadas.

- `APP_PASSWORD_HASH`: el hash de tu contraseña (nunca la contraseña).
- `SESSION_SECRET`: firma la cookie de sesión. Cambiarla cierra todas las
  sesiones (paso 13.4).
- `COOKIE_SECURE=true`: la cookie de sesión solo viaja por HTTPS.
- Opcionales (ver `.env.example`): `MAX_INTENTOS`, `BLOQUEO_MINUTOS`. Para
  añadirlas: `sudo nano /etc/finanzas/finanzas.env`. `GMAIL_REMITENTE` ya no se
  usa desde el ítem 27: si la tienes, déjala vacía o bórrala (con una dirección
  distinta de las dos oficiales la app no arranca).

### 7.2 `/etc/finanzas/duckdns.env` (root, 0600)

Aquí va el token de DuckDNS. Solo root puede leerlo.

```bash
# En la VM
sudo install -o root -g root -m 0600 /dev/null /etc/finanzas/duckdns.env
sudo nano /etc/finanzas/duckdns.env
```

Escribe estas dos líneas con tus datos (solo el subdominio, sin
`.duckdns.org`, y el token del paso 3):

```
DUCKDNS_DOMINIO=tu-subdominio
DUCKDNS_TOKEN=pega-aqui-tu-token
```

Guarda con `Ctrl+O` y `Enter`, y sal con `Ctrl+X`. Se usa `nano` para que el
token no quede en el historial de comandos.

---

## 8. Gmail

Hay dos formas de autorizar el acceso de solo lectura a Gmail. Las dos dejan el
mismo token en `/var/lib/finanzas/gmail/token.json`; elige una.

- **Opción A: en tu computador personal.** El comando abre el navegador del
  mismo equipo. Necesita Python y una copia del repositorio en ese computador,
  y luego copiar el token a la VM.
- **Opción B: desde la VM, sin navegador.** Recomendada si usas un computador
  compartido (por ejemplo, el de la universidad) con Cloud Shell. El comando se
  ejecuta **en la VM**; tú solo abres un enlace en el navegador y pegas en la
  terminal la dirección a la que te lleva Google. Ni el token ni el JSON del
  cliente se guardan en el computador compartido.

> **Computadores compartidos.** No hagas la opción A en un computador
> compartido: allí quedarían el `client_secret_....json` y el token, y el token
> da lectura a **todo** tu correo. Usa la opción B.
>
> Todo lo demás de esta guía se puede hacer desde cualquier computador (con
> Cloud Shell, paso 1.2). Y una vez autorizada, la app sincroniza sola desde
> la VM: tu computador puede estar apagado.

### 8.1 Opción A: en tu computador personal

> Para copiar el token a la VM (punto 2) hace falta una llave SSH en tu
> computador personal. Si solo creaste la de Cloud Shell, añade antes la de tu
> computador como segunda llave (paso 1.2, opción B, último punto).

1. Sigue en tu computador los pasos 1 a 6 de la sección
   [la guía de Gmail personal](../docs/GMAIL.md). Al terminar tendrás
   `~/token_gmail.json`.
2. Déjalo legible solo por ti y cópialo a la VM con `scp`:

   ```bash
   # En tu computador (en Windows, chmod no existe: sáltate esa línea)
   chmod 600 ~/token_gmail.json
   scp -i ~/.ssh/oracle_finanzas ~/token_gmail.json ubuntu@203.0.113.10:token_gmail.json
   ```

3. En la VM, muévelo a su sitio con el dueño y los permisos correctos, y borra
   la copia intermedia:

   ```bash
   # En la VM
   sudo install -o finanzas -g finanzas -m 0600 ~/token_gmail.json /var/lib/finanzas/gmail/token.json
   rm ~/token_gmail.json
   sudo stat -c '%U:%G %a %n' /var/lib/finanzas/gmail /var/lib/finanzas/gmail/token.json
   ```

   Debe mostrar `finanzas:finanzas 700` para la carpeta y `finanzas:finanzas 600`
   para el token. La carpeta es del usuario `finanzas` para que la app pueda
   guardar el token cuando lo renueva (cada hora).

4. Borra también `~/token_gmail.json` de tu computador. El JSON del cliente
   OAuth (`client_secret_....json`) no hace falta en la VM.

### 8.2 Opción B: desde la VM (sin navegador), recomendada si usas un computador compartido

Todo se hace desde Cloud Shell conectado a la VM (paso 1.4) y con el navegador
del computador. Usa una **ventana privada** del navegador para Google Cloud y
para el enlace de autorización: así no quedan sesiones ni historial.

1. **Crea el cliente OAuth en Google Cloud.** Haz los pasos 1 a 5 de
   [la guía de Gmail personal](../docs/GMAIL.md): tipo **"App de
   escritorio"**. En el paso 5, **no descargues el JSON** si puedes evitarlo.

   Al crear el cliente, Google muestra una ventana con el **ID de cliente** y el
   **secreto del cliente**, cada uno con un botón para copiarlo. Déjala abierta:
   los copiarás en el punto 2. **Ojo:** en la consola actual, el secreto
   completo solo se ve en esa ventana; si la cierras, después no se puede volver
   a ver (habría que crear un secreto nuevo en el cliente, o un cliente nuevo).

   Si la consola solo te deja descargarlo: descarga el JSON, ábrelo con el
   Bloc de notas, copia todo su contenido y pégalo en el punto 2 (con `nano`, en
   vez de la plantilla). Después **borra el archivo, vacía la papelera** y
   borra la descarga del historial del navegador. No es perfecto: el archivo
   pasa unos minutos por el disco del computador compartido. Por eso es mejor
   copiar los dos campos desde la ventana.

   El portapapeles también guarda lo último que copiaste: al terminar, copia
   cualquier otro texto para reemplazarlo.

2. **Crea el JSON del cliente en la VM**, como usuario `finanzas`, con permisos
   0600. La carpeta `/var/lib/finanzas/gmail` ya existe (paso 5.2). Primero
   crea el archivo vacío con el dueño y los permisos correctos, y luego ábrelo
   con `nano`:

   ```bash
   # En la VM
   sudo install -o finanzas -g finanzas -m 0600 /dev/null /var/lib/finanzas/gmail/client_secret.json
   sudo -u finanzas nano /var/lib/finanzas/gmail/client_secret.json
   ```

   Pega esta plantilla y reemplaza `TU_ID_DE_CLIENTE` y `TU_SECRETO_DE_CLIENTE`
   por lo que copiaste en el punto 1 (el ID termina en
   `.apps.googleusercontent.com`; deja las comillas):

   ```json
   {"installed": {
     "client_id": "TU_ID_DE_CLIENTE",
     "client_secret": "TU_SECRETO_DE_CLIENTE",
     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
     "token_uri": "https://oauth2.googleapis.com/token",
     "redirect_uris": ["http://localhost"]
   }}
   ```

   Guarda con `Ctrl+O` y `Enter`, y sal con `Ctrl+X`. Si en cambio pegas el JSON
   descargado completo, sirve igual.

   Otra forma, sin editor: `sudo -u finanzas tee /var/lib/finanzas/gmail/client_secret.json > /dev/null`,
   pega el JSON, pulsa `Enter` y luego `Ctrl+D`. Con `install` previo el
   archivo ya queda `finanzas:finanzas 600`; `tee` lo reescribe sin cambiar
   eso. Los dos métodos evitan que el secreto quede en el historial de comandos.

3. **Ejecuta la autorización en la VM**, como `finanzas` y desde `/opt/finanzas`
   (no necesita `finanzas.env` ni ninguna variable de entorno):

   ```bash
   # En la VM
   cd /opt/finanzas && sudo -u finanzas .venv/bin/python -m finanzas.gmail autorizar --sin-navegador \
       --credenciales /var/lib/finanzas/gmail/client_secret.json \
       --token /var/lib/finanzas/gmail/token.json --borrar-credenciales
   ```

4. **Qué verás y qué copiar.** El comando muestra un enlace largo que empieza
   por `https://accounts.google.com/`, y espera en `Dirección:`.
   - Copia el enlace (en Cloud Shell, selecciónalo con el ratón y usa
     `Ctrl+C` o el menú del botón derecho) y ábrelo en la ventana privada.
   - Elige tu cuenta de Gmail. Verás la advertencia **"Google no verificó esta
     app"**, la del paso 4 del README: pulsa "Configuración avanzada" → "Ir a
     ... (no seguro)" y acepta el permiso de **solo lectura**.
   - El navegador irá a una página que empieza por `http://localhost:1/`.
     **Es normal que el navegador muestre un error** (`ERR_UNSAFE_PORT` o "No
     se puede acceder a este sitio" en Chrome, "Esta dirección está
     restringida" en Firefox): el puerto 1 se eligió a propósito para que no
     haya nada ahí. Aun así, la dirección con el código queda en la barra.
     Copia la dirección **completa** de la barra, que empieza por
     `http://localhost:1/`. Si Chrome la muestra sin el `http://`
     (`localhost:1/?state=...`), cópiala tal cual: también se acepta.
   - Pégala en Cloud Shell y pulsa `Enter`. Tienes 3 intentos; si falla, el
     mensaje dice por qué, sin mostrar la dirección. Si al pegar ves algo como
     `^[[200~` alrededor, no pasa nada: el comando lo quita.

   Hazlo en pocos minutos: el código de la dirección caduca pronto y solo sirve
   una vez. Además, solo lo puede canjear este mismo comando (va ligado a un
   valor aleatorio que solo existe en su memoria, PKCE). El comando nunca
   imprime el token, el código ni el secreto.

   Si todo va bien verás `Token guardado en /var/lib/finanzas/gmail/token.json con permisos 0600.`
   y `Se borró el archivo de credenciales ...`. Si algo falla no se guarda nada
   ni se borra el JSON del cliente: vuelve a ejecutar el punto 3.

   ¿Por qué se puede borrar el JSON del cliente? El token guarda el ID y el
   secreto del cliente junto con el permiso de renovación (refresh token), que
   es lo que la app necesita para renovarlo sola. Si no usaste
   `--borrar-credenciales`, bórralo tú:
   `sudo -u finanzas rm /var/lib/finanzas/gmail/client_secret.json`.

5. **Comprueba el dueño y los permisos** del token:

   ```bash
   sudo stat -c '%U:%G %a %n' /var/lib/finanzas/gmail/token.json
   ```

   Debe mostrar `finanzas:finanzas 600`.

6. **Prueba una sincronización.** Si ya hiciste la sección 10 (por ejemplo,
   porque estás volviendo a autorizar), lánzala y mira el resultado:

   ```bash
   sudo systemctl start finanzas-sync.service
   journalctl -u finanzas-sync -n 5 --no-pager
   ```

   Si aún no llegas a la sección 10, se comprobará en la sección 11.

Al terminar, cierra la ventana privada del navegador.

---

## 9. Caddy (HTTPS)

Caddy recibe las visitas por HTTPS, obtiene y renueva solo el certificado, y
se las pasa a la app.

### 9.1 Instalar Caddy desde su repositorio oficial

```bash
# En la VM
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

(Son los comandos de <https://caddyserver.com/docs/install#debian-ubuntu-raspbian>.
Si cambian, sigue los de esa página.)

### 9.2 El Caddyfile y el dominio

El archivo `deploy/caddy/Caddyfile` usa `{$DOMINIO}`, que se toma de una
variable de entorno del servicio de Caddy. Se define en un "override" de
systemd (un archivo que ajusta el servicio sin tocar el original):

```bash
# En la VM (cambia tu-subdominio)
sudo cp /opt/finanzas/deploy/caddy/Caddyfile /etc/caddy/Caddyfile
sudo mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironment=DOMINIO=%s\n' 'tu-subdominio.duckdns.org' \
    | sudo tee /etc/systemd/system/caddy.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart caddy
sudo systemctl status caddy --no-pager
```

(Alternativa: escribir el dominio directamente en `/etc/caddy/Caddyfile` en
lugar de `{$DOMINIO}`.)

Qué hace el Caddyfile y por qué (los comentarios del archivo lo explican):

- Pasa todo a `127.0.0.1:8000`, escrito así y no como `localhost`.
- **No** cambia el encabezado `Host`: la app lo compara con `Origin` para
  frenar formularios enviados desde otros sitios (CSRF).
- Pone `X-Forwarded-For` con la IP real del visitante (e ignora la que el
  visitante diga), que es la que usa el límite de intentos de login.
- Añade HSTS: el navegador recordará usar siempre HTTPS con tu subdominio.

Para ver si el certificado se emitió, busca esa frase en el registro de Caddy
(puede tardar uno o dos minutos después de `restart`):

```bash
# En la VM
journalctl -u caddy --no-pager | grep -i "certificate obtained successfully"
```

Si muestra una línea con tu subdominio, el certificado está listo. Si no
muestra nada, espera un poco y repite; para ver todo el registro:
`journalctl -u caddy -n 50 --no-pager`.

Qué es normal ver en ese registro en este momento:

- Al principio, líneas con `"creating new account because no account for
  ... is known"` y con `"error":"open .../default.json"`. Son de nivel `info`:
  Caddy avisa que es la primera vez y crea su cuenta de Let's Encrypt.
- Hasta el paso 10 la app no está encendida: Caddy responderá "502" y el
  registro mostrará errores con `connection refused` hacia `127.0.0.1:8000`.
- Poco después de emitir el certificado llegan visitas de robots que no
  conoces. Los certificados se publican en registros públicos y hay robots que
  los leen y prueban los dominios nuevos. Solo verán la página de login (con
  el límite de intentos).

---

## 10. Servicios y temporizadores de systemd

```bash
# En la VM
sudo cp /opt/finanzas/deploy/systemd/*.service /opt/finanzas/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start finanzas-migrar.service      # crea la base (sus tablas y categorías)
journalctl -u finanzas-migrar -n 5 --no-pager     # debe terminar con "Listo: la base está en la revisión ..."
sudo systemctl enable --now finanzas.service
sudo systemctl enable --now finanzas-sync.timer finanzas-respaldo.timer duckdns.timer

# Probar ya DuckDNS, sin esperar al temporizador
sudo systemctl start duckdns.service
journalctl -u duckdns -n 5 --no-pager            # debe decir "IP actualizada (OK)"
systemctl list-timers 'finanzas*' 'duckdns*'
```

| Unidad | Qué hace |
|---|---|
| `finanzas-migrar.service` | `python -m finanzas.migrar`: crea la base o le aplica las migraciones pendientes, con respaldo previo. No tiene temporizador: se lanza a mano al instalar y al actualizar (13.2). Al lanzarlo detiene `finanzas` y `finanzas-sync` (`Conflicts=`), para que nada escriba mientras migra; después hay que arrancarlos de nuevo. |
| `finanzas.service` | La app web (uvicorn, un solo proceso, solo en 127.0.0.1:8000). No arranca si la base no está migrada. |
| `finanzas-sync.timer` → `finanzas-sync.service` | `python -m finanzas.sincronizacion` a las 00, 06, 12 y 18 h (con hasta 5 min de azar). Si la VM estaba apagada, sincroniza al arrancar. |
| `finanzas-respaldo.timer` → `finanzas-respaldo.service` | `deploy/respaldo.py` todos los días a las 03:30. Conserva el de hoy y los de los 14 días anteriores. |
| `duckdns.timer` → `duckdns.service` | Actualiza la IP de DuckDNS al arrancar y cada 30 minutos. |

Los servicios de la app corren como `finanzas`, con el disco en solo lectura
salvo `/var/lib/finanzas` (y `/var/backups/finanzas` para el respaldo), sin
privilegios y con otras restricciones de systemd. El de DuckDNS corre con un
usuario temporal (`DynamicUser`): systemd, como root, lee
`/etc/finanzas/duckdns.env` y se lo entrega en privado (`LoadCredential`); el
script pasa el token a `curl` por la entrada estándar, así que no aparece en la
lista de procesos ni en los registros.

---

## 11. Primer uso

1. Abre `https://tu-subdominio.duckdns.org` en el navegador. Debe verse el
   candado y la página de login.
2. Entra con tu contraseña.
3. Ve a **Saldo** y configura el saldo inicial y la fecha de inicio (lee
   "Saldo, ingresos y ajustes" en el README: el saldo es el que tenías al
   comenzar ese día).
4. Pulsa **Sincronizar ahora**. Deben aparecer tus movimientos desde la fecha
   de inicio.
5. Lanza una vez la sincronización programada para comprobar que también
   funciona (y para que la verificación del paso 12 tenga un resultado):

   ```bash
   # En la VM
   sudo systemctl start finanzas-sync.service
   journalctl -u finanzas-sync -n 5 --no-pager
   ```

6. Lanza también un respaldo, para no esperar al de las 03:30. La base la creó
   `finanzas-migrar` (paso 10); si dice "no existe la base de origen", revisa
   `journalctl -u finanzas-migrar -n 20 --no-pager`:

   ```bash
   # En la VM
   sudo systemctl start finanzas-respaldo.service
   journalctl -u finanzas-respaldo -n 5 --no-pager  # "Respaldo creado: finanzas-AAAA-MM-DD.db"
   ```

**Si en alguna prueba anterior quedaron avisos "Recibiste" como no
reconocidos** (por ejemplo, si copiaste a la VM una base de antes del ítem 09),
hay que reprocesarlos para que entren como ingresos (D12). Con una base nueva
no hace falta. Se sigue el apartado "Reprocesar los correos no reconocidos" del
README, con las rutas y el usuario del servidor:

```bash
# En la VM
sudo -u finanzas sqlite3 /var/lib/finanzas/finanzas.db "DELETE FROM correos_no_reconocidos;"
sudo systemctl start finanzas-sync.service
journalctl -u finanzas-sync -n 5 --no-pager
```

Los que sigan sin reconocerse vuelven a quedar registrados; los movimientos ya
guardados no se duplican.

### 11.1 Instalar la app en el celular

La app nueva (`/app`) se puede instalar en la pantalla de inicio: abre como una
app, con su ícono (la hoja de libreta) y el nombre «Finanzas», sin la barra
del navegador. Solo funciona con HTTPS, que ya tienes (paso 9).

**Android (Chrome):**

1. Abre `https://tu-subdominio.duckdns.org/app/` en Chrome.
2. Toca el menú **⋮** y luego **Instalar app** (o **Agregar a la pantalla
   principal**).
3. Confirma con **Instalar**. El ícono «Finanzas» aparece en la pantalla de
   inicio.

**iPhone (Safari):**

1. Abre `https://tu-subdominio.duckdns.org/app/` en **Safari** (otros
   navegadores del iPhone pueden no ofrecerlo).
2. Toca **Compartir** (el cuadrado con la flecha hacia arriba).
3. Toca **Agregar a inicio** y luego **Agregar**.

La sesión es la misma cookie de siempre: entras con tu contraseña la primera
vez y dura lo mismo (hasta 7 días). Si pierdes el celular, sigue 13.4.

**Qué guarda el celular.** Solo los archivos de la app (código, estilos,
fuentes e íconos de esta versión), nunca tus movimientos ni saldos: lo que
llega de `/api` va siempre directo al servidor y no se guarda. Sin conexión,
la app abre y dice "No hay conexión con la app…", sin mostrar datos. Al cerrar
sesión o al publicar una versión nueva se borra lo guardado de versiones
anteriores.

**Comprobar que funciona** (después de cada despliegue que toque el frontend):

```bash
# En tu computador
curl -sI https://tu-subdominio.duckdns.org/app/manifest.webmanifest | grep -i content-type  # application/manifest+json
curl -sI https://tu-subdominio.duckdns.org/app/sw.js | grep -iE "content-type|cache-control" # text/javascript y no-store
```

En Chrome del computador, abre `https://tu-subdominio.duckdns.org/app/`, pulsa
F12 y ve a **Application**: en **Manifest** no debe haber errores ni avisos de
instalación; en **Service workers**, `sw.js` aparece "activated and is
running"; en **Cache Storage** hay una sola caché `finanzas-cascaron-…` y
ninguna dirección empieza por `/api`. En el celular, abre la app instalada:
debe abrir sin barra del navegador.

---

## 12. Verificación

```bash
# En la VM
sudo bash /opt/finanzas/deploy/verificar.sh tu-subdominio.duckdns.org
```

Imprime ✔ o ✘ por cada comprobación, con una pista para cada fallo, y no
muestra ningún secreto. Comprueba:

- que `finanzas`, `caddy` y los tres temporizadores están activos y habilitados;
- que la última sincronización programada terminó con código 0;
- que existe el respaldo de hoy o de ayer (con permisos 600);
- que `https://…/app/` responde 200 con HSTS, Content-Security-Policy estricta
  (scripts y estilos solo del propio sitio) y `Cache-Control: no-store`, y que
  `http://…` redirige a `https://`;
- que el frontend está compilado (`frontend/dist`) y que `https://…/` redirige
  a `/app/`;
- que `https://…/api/sesion` sin sesión responde 401 en JSON, y que
  `manifest.webmanifest` y `sw.js` responden 200;
- que la app solo escucha en `127.0.0.1` y que no hay puertos TCP públicos
  aparte de 22, 80 y 443; que `iptables` acepta 80 y 443 antes del REJECT;
- los permisos de `/etc/finanzas/*.env`, de las carpetas, de la base y del
  token de Gmail;
- que `COOKIE_SECURE=true`.

Si todo está bien termina con "Todo en orden." Desde tu computador puedes
comprobar además que el puerto de la app no está expuesto:
`curl -m 5 http://tu-subdominio.duckdns.org:8000` debe fallar.

> **Si solo fallan las comprobaciones HTTPS** (`https://…/app/` y la
> redirección de `http://…`), prueba desde tu computador:
>
> ```bash
> # En tu computador
> curl -I https://tu-subdominio.duckdns.org/app/
> ```
>
> La red de Oracle puede no permitir que la VM se llame a sí misma por su IP
> pública. Si desde tu computador responde `HTTP/2 200` con
> `strict-transport-security`, `content-security-policy` y
> `cache-control: no-store`, el despliegue está bien.

---

## 13. Operación

### 13.1 Ver los registros (logs)

Todos los registros van a journald. Ninguno lleva montos, cuentas ni contenido
de correos.

```bash
# En la VM
journalctl -u finanzas -f                       # la app, en vivo (Ctrl+C para salir)
journalctl -u finanzas-sync --since today       # sincronizaciones de hoy
journalctl -u finanzas-respaldo -n 20
journalctl -u duckdns -n 20
journalctl -u caddy -n 50
systemctl list-timers 'finanzas*' 'duckdns*'    # próximas ejecuciones
systemctl status finanzas finanzas-sync --no-pager
```

### 13.2 Actualizar la app

Cuando haya una versión nueva en `main`. Todos los comandos son **en la VM**;
pégalos de uno en uno y mira el resultado de cada uno.

```bash
# En la VM
sudo systemctl start finanzas-respaldo.service   # 1. respaldo manual antes de cambiar nada
sudo systemctl stop finanzas-sync.timer finanzas-respaldo.timer finanzas-sync.service finanzas.service   # 2. parar la app y los temporizadores
cd /opt/finanzas
sudo git pull --ff-only
sudo .venv/bin/pip install -r backend/requirements.txt -e .
cd /opt/finanzas/frontend && sudo env PATH=/opt/node/bin:/usr/bin:/bin npm ci --ignore-scripts   # compilar el frontend nuevo (/app), ver 6.1
sudo env PATH=/opt/node/bin:/usr/bin:/bin npm run build
cd /opt/finanzas   # volver a la carpeta del código (aunque la compilación haya fallado)
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start finanzas-migrar.service     # 3. migrar la base (hace otro respaldo antes, si hay cambios)
journalctl -u finanzas-migrar -n 20 --no-pager   # 4. leer qué hizo
sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer   # 5. arrancar de nuevo
diff deploy/caddy/Caddyfile /etc/caddy/Caddyfile || echo "El Caddyfile cambió: revisa el paso 9.2"
sudo bash deploy/verificar.sh tu-subdominio.duckdns.org
```

Si el Caddyfile cambió, cópialo de nuevo y aplica con `sudo systemctl reload caddy`.

**Todo lo anterior en un solo comando: `deploy/desplegar.sh`.** Hace los mismos
pasos con el commit exacto que le indiques (debe estar en `main`). Toma un
candado, para que nunca corran dos despliegues a la vez, y comprueba al final
que la app responde. Si el commit trae migraciones nuevas, se detiene sin tocar
nada hasta que lo autorices con `--permitir-migraciones`.

```bash
# En la VM: desplegar el último commit de main
sudo git -C /opt/finanzas fetch origin && sudo git -C /opt/finanzas log origin/main --oneline -3
sudo bash /opt/finanzas/deploy/desplegar.sh "$(sudo git -C /opt/finanzas rev-parse origin/main)"
```

Cómo terminar, según el código de salida:

| Código | Qué pasó |
|---|---|
| `0` | Desplegado: la app responde. Después corre `verificar.sh` como diagnóstico. |
| `1` | Falló sin cambiar la base (o falló la migración, que deja la base como estaba): volvió solo al commit anterior y la app responde. |
| `2` | Uso incorrecto: commit mal escrito, fuera de `main` o sin dominio en el override de Caddy. No se tocó nada. |
| `3` | El despliegue migraría la base: revisa en esta guía la sección de esas migraciones y repite con `--permitir-migraciones`. No se tocó nada. |
| `4` | Falló con la base **ya migrada**: no vuelve atrás solo, porque el código anterior no entiende la base nueva. Sigue "Volver atrás", caso 2. |
| `5` | La vuelta atrás quedó incompleta o la app no responde: revisa **ya** con `journalctl -u finanzas -n 50 --no-pager`. |
| `6` | No se hizo nada: otro despliegue en curso, no se pudo traer el código, falló el respaldo, o el commit es más viejo que la base. |

Lo que conviene saber:

- Decide si hay migraciones mirando la **revisión real de la base** (con
  `sqlite3`, en solo lectura), no solo el código: también frena si la base
  quedó atrás por un `--bajar-a` o una caída a medias.
- Comprueba la app de **esta** VM (pide `https://tu-dominio` a `127.0.0.1`),
  aunque DuckDNS apunte a otra.
- Si se corta la sesión SSH a mitad, vuelve atrás solo (si la base no
  cambió). Aun así, para despliegues largos usa `tmux`.
- No hace la prueba en seco del lector ni los pasos propios de cada
  migración: si la versión cambia cómo se leen los avisos, o la sección de
  una migración pide algo más, sigue la vía manual de arriba.
- Corre la copia de `desplegar.sh` que ya está en la VM: la **primera vez**
  (cuando la VM todavía no lo tiene) despliega a mano con los pasos de
  arriba.
- Deja `/opt/finanzas` en el commit exacto, sin rama ("detached"). Antes de
  volver a la vía manual (`git pull --ff-only`), ejecuta
  `sudo git -C /opt/finanzas checkout main`.
- Cada despliegue queda anotado en `/var/lib/finanzas-despliegue/historial.log`.

**Frontend nuevo (`/app`).** Las dos líneas de `npm` compilan el frontend de la
versión que acabas de bajar. Si `/opt/node/bin/node` no existe (tu VM se
instaló antes del ítem 12), instala primero Node con el paso 6.1 y vuelve a
esas dos líneas. Deben terminar con `✓ built in …`. Si `npm run build` falla:

- **en la comprobación de tipos** (primer paso, `tsc`: errores con `error TS…`),
  no se llega a compilar y `frontend/dist` queda **intacto**;
- **en la compilación** (segundo paso, `vite build`: errores después de
  `vite … building`), Vite solo vacía `frontend/dist` al escribir el resultado,
  así que un error al compilar también lo deja intacto. Solo un fallo mientras
  escribe los archivos (por ejemplo, disco lleno) puede dejarlo vacío o a
  medias; entonces `/app` responde "no está compilado" o muestra la pantalla en
  blanco.

En los dos primeros casos `/app` sigue sirviendo **el frontend anterior**, que
puede no entenderse del todo con la API nueva: no lo uses hasta resolverlo y
pide ayuda con el error. La API sigue funcionando en todos los casos, pero
ya no hay una interfaz v1 a la que recurrir: sin un `frontend/dist` válido la
app no se puede usar. Después de arrancar, abre `https://tu-subdominio.duckdns.org/app/`
en el celular y en el computador: debe mostrar la pantalla "Entrar".
La app instalada en el celular (11.1) toma la versión nueva sola: la próxima
vez que la abras con conexión descarga los archivos nuevos y borra los viejos;
si sigue viéndose la anterior, ciérrala del todo y vuelve a abrirla.

#### Prueba en seco antes de desplegar un cambio del lector (opcional)

Si la versión nueva cambia cómo se leen los avisos (por ejemplo, el ítem 21:
avisos citados), compruébala con tus correos reales **antes** del paso 5
(arrancar de nuevo). El repositorio solo tiene correos inventados; esta
prueba vuelve a descargar de Gmail (solo lectura) los correos que ya están en
tu base y dice cómo los leería el código nuevo. **No escribe nada** (la base
se abre en solo lectura) y solo muestra conteos y fechas, nunca montos,
nombres ni asuntos. En la VM, de uno en uno, justo después del paso 4:

```bash
# En la VM
sudo systemctl start finanzas-prueba-en-seco.service
journalctl -u finanzas-prueba-en-seco -n 60 --no-pager
```

Cómo leerlo:

- En la línea `movimiento guardado (...)`, lo normal es que **todos** sean
  `aviso válido`. Si alguno sale `citado` o `no reconocido`, la lista de abajo
  da la fecha del correo: búscalo en la app y en Gmail. Si era un aviso
  normal, **no sigas**: vuelve al código anterior ("Volver atrás", abajo) y
  pide ayuda con esa fecha; se pedirá el cuerpo de ese correo anonimizado
  para crear un fixture. Si de verdad era un reverso u otro correo que citaba
  un aviso, el código nuevo acierta y puedes seguir.
- En `no reconocido guardado (...)`, los que salen `aviso válido` se
  recuperan reprocesando (README, "Reprocesar los correos no reconocidos").
  Los `rechazado por remitente o autenticación` son normales si eran
  correos falsos.
- "No se pudo guardar el token de Gmail renovado" es esperado aquí: la unidad
  no puede escribir en ningún sitio.

**Ver qué hay delante del aviso (`--mostrar-previo`, diagnóstico).** Si
avisos normales salen `citado` o `no reconocido`, esta opción muestra, para
cada uno de esos correos y por cada versión del cuerpo (primero `text/plain`,
después `HTML`, el mismo orden que usa la sincronización):

- el estado de esa versión (`valido`, `citado` o `sin_aviso`);
- `previo`: el texto, tal como lo ve el lector (ya sin los invisibles de
  formato y con los espacios colapsados), que hay **antes** del primer
  "Bancolombia: Compraste/Transferiste/Recibiste...". Si esa versión no tiene
  ningún inicio de aviso, sus primeros 200 caracteres, cortados antes de
  cualquier "Compraste", "Transferiste", "Recibiste" o "Bancolombia:";
- `clave`: lo que de verdad se compara con los encabezados permitidos (solo
  letras y dígitos, sin tildes, en minúsculas).

Todo va enmascarado: cada dígito sale como `#`, cada dirección de correo como
`[correo]`, y los caracteres invisibles o raros que quedan (por ejemplo
`ㅤ` o `⠀`, rellenos típicos de los preencabezados ocultos) se
escriben como `\uXXXX` para que se vean. Si el texto pasa de 300 caracteres
se muestran los primeros y los últimos 150 y se dice la longitud original.
**Nunca** muestra el aviso ni lo que va después (montos, comercios, cuentas).
Los correos rechazados por remitente o autenticación no se muestran.

> **Antes de compartir la salida o una captura, revísala:** puede traer
> texto de la plantilla del banco y quizá tu nombre o parte de él. Tapa lo
> personal. Los dígitos y los correos ya salen tapados.

Cómo correrla en la VM **sin tocar la app en marcha**, con un código distinto
del desplegado (por ejemplo, la app sigue en la v1 y quieres probar
`--mostrar-previo`, que llega con una versión nueva): se baja el código nuevo
a una carpeta aparte, se ejecuta una sola vez como el usuario `finanzas`, con
la base en solo lectura, y se borra la carpeta. No hace falta parar nada ni
migrar: la prueba en seco abre la base directamente con sqlite en solo
lectura y no exige la última revisión de migraciones. En la VM, de uno en uno:

```bash
# En la VM
sudo git -C /opt/finanzas fetch origin                      # 1. traer el código nuevo (no cambia /opt/finanzas)
sudo git -C /opt/finanzas worktree add --detach /opt/finanzas-prueba origin/main   # 2. copia aparte
sudo systemd-run --wait --pipe --quiet \
  -p User=finanzas -p Group=finanzas \
  -p EnvironmentFile=/etc/finanzas/finanzas.env \
  -p WorkingDirectory=/opt/finanzas-prueba \
  -p Environment=PYTHONDONTWRITEBYTECODE=1 \
  -p Environment=PYTHONPATH=/opt/finanzas-prueba/backend:/opt/finanzas-prueba \
  -p ProtectSystem=strict -p ReadOnlyPaths=/var/lib/finanzas \
  -p ProtectHome=true -p PrivateTmp=true -p NoNewPrivileges=true \
  /opt/finanzas/.venv/bin/python -m finanzas.prueba_en_seco --incluir-no-reconocidos --mostrar-previo   # 3. la prueba
sudo git -C /opt/finanzas worktree remove --force /opt/finanzas-prueba   # 4. borrar la copia aparte
```

Notas sobre la receta:

- En el paso 2, `origin/main` sirve cuando la opción ya está en `main`. Si el
  equipo te pide probar otra versión, cambia `origin/main` por la rama o el
  commit que te indiquen (por ejemplo `origin/develop`). Si el paso 2 dice que
  `/opt/finanzas-prueba` ya existe (quedó de una vez anterior), haz primero el
  paso 4.
- Por qué funciona: `PYTHONPATH` antepone el paquete del worktree de prueba
  (en `backend/` desde esta reorganización; en la raíz para versiones previas)
  al paquete editable instalado en el entorno de la app. Así corre el código
  elegido en el paso 2, mientras las librerías salen de `/opt/finanzas/.venv`.
  Antes de usar otro commit, comprueba si requiere dependencias nuevas; esta
  receta solo reutiliza las ya instaladas.
  La copia la crea root con permisos normales (carpetas 755, archivos 644),
  así que `finanzas` puede leerla pero no cambiarla.
- La salida sale directo en la terminal (`--pipe`), no en `journalctl`.
- Con `ProtectSystem=strict` y `ReadOnlyPaths=/var/lib/finanzas`, la prueba no
  puede escribir en ningún sitio: igual que con la unidad de arriba, "No se
  pudo guardar el token de Gmail renovado" es esperado.
- La app, la sincronización y los respaldos siguen corriendo con el código de
  `/opt/finanzas`: el paso 1 solo actualiza las referencias de git (no el
  código en uso), y el 2 y el 4 solo tocan `/opt/finanzas-prueba` y la lista
  de copias de git.

#### Desplegar la reorganización (`backend/`) y, si falta, la migración 0012

Se aplica con el procedimiento normal de 13.2, sin pasos extra, pero **no te
saltes la línea de `pip`**:

- **El paquete se movió a `backend/`:** desde esta versión, `requirements.txt`
  está en `backend/` y el código se instala como paquete editable. En 13.2, la
  línea `sudo .venv/bin/pip install -r backend/requirements.txt -e .` va
  **antes** de `finanzas-migrar`: sin ella los servicios no encuentran
  `finanzas` y no arrancan.
- **Migración 0012 (descartes reversibles de movimientos automáticos):** ya
  estaba en `main` antes de la reorganización. Si tu VM sigue en la 0011,
  `finanzas-migrar` la aplica ahora: agrega la tabla de descartes y dos
  columnas a las preguntas de la conciliación, sin cambiar montos, fechas ni
  categorías, y deja antes el respaldo `finanzas-antes-de-migrar-0011-*.db`
  en `/var/backups/finanzas` (compruébalo antes de arrancar la app). Si la VM
  ya está en la 0012, `finanzas-migrar` lo dice («La base ya está al día
  (revisión 0012). No se cambió nada.») y no crea respaldo previo.

**Volver atrás de la 0012.** `--bajar-a 0011` solo funciona mientras no haya
**historial** de descartes (también bloquean los ya restaurados) ni preguntas
del banco respondidas eligiendo un movimiento u ocurrencia; si los hay, se
niega sin tocar nada y hay que restaurar el respaldo previo ("Volver atrás",
caso 2). El orden importa: **primero** detén la app y los temporizadores (la
línea `systemctl stop` del caso 2) y baja con el código actual (el que trae
la 0012); **después** vuelve al commit anterior con el comando de "Volver
atrás", caso 1, que ya reinstala desde la raíz el código anterior a
`backend/`.

#### Desplegar el ítem 29 (motor de conciliación, migración 0008)

La migración 0008 reconstruye la tabla `movimientos` (conserva todos los
movimientos con sus ids; el saldo no cambia), le agrega el estado frente al
banco (`confirmado`, `provisional`, `sin aviso`), el destino de 4 dígitos y la
marca "no está en el banco", y crea las tablas de importaciones y de
preguntas, vacías. Tus ingresos manuales pasan a `provisional`. **Antes de
migrar, haz el respaldo previo** (D26): `finanzas-migrar` lo hace solo, pero
comprueba que quedó `finanzas-antes-de-migrar-0007-*.db` en
`/var/backups/finanzas` antes de arrancar la app.

Esta versión todavía **no** tiene botón para importar (es el ítem 30): solo
trae el motor y la conciliación en seco, para que lo valides con tus datos
antes de activar la importación.

**Volver atrás de la 0008.** Se deshace con `--bajar-a 0007` ("Volver atrás",
abajo) mientras no haya nada de la conciliación guardado (movimientos
importados, confirmados o marcados, importaciones o preguntas); si lo hay, se
niega sin tocar nada y hay que restaurar el respaldo previo a la migración.

#### Desplegar el ítem 30 (importación interactiva, migración 0010)

Antes de activar la importación, valida el motor en seco con tu Excel real (D44).
No copies ese archivo al repositorio. La migración 0010 requiere respaldo previo
explícito: ejecuta el paso habitual `finanzas-migrar` y comprueba el archivo
`finanzas-antes-de-migrar-0009-*.db` en `/var/backups/finanzas` antes de arrancar
la aplicación. Si vienes desde una revisión anterior, comprueba el respaldo
que corresponda a esa revisión; no presupongas que la base ya estaba en la 0009.

El proceso web sigue siendo único: los análisis (15 min) y el «Deshacer» (30 s) viven en
memoria y se pierden al reiniciar, sin dejar archivos subidos. Una confirmación
con 409 pide volver a analizar; no repitas automáticamente la petición.

Se puede bajar a la 0009 solo mientras no se haya usado la información nueva.
Con importaciones reversibles, reglas bancarias o revisiones/borrados lógicos,
se niega sin cambiar nada: restaura el respaldo previo mediante el procedimiento
de esta guía. No se borra el diario para forzar un downgrade.
#### Desplegar el ítem 41 (destinos del correo, migración 0009)

**Antes de migrar, comprueba el respaldo previo** (D26). El servicio
`finanzas-migrar` lo crea automáticamente: conserva la copia
`finanzas-antes-de-migrar-0008-*.db` de `/var/backups/finanzas` antes de
arrancar la app. Si actualizas desde una revisión anterior, la copia lleva
esa revisión en el nombre y protege todos los cambios aplicados juntos.
No borres esa copia tras comprobar que la migración terminó.

La 0009 recorta los destinos numéricos de movimientos, preguntas del correo
y reglas al formato `*1234`. No cambia montos, fechas, categorías ni ids de
movimientos. Las reglas con idénticas condiciones y categoría se consolidan
en el menor id y los movimientos apuntan a él; reglas con condiciones de
monto diferentes se mantienen.

Si destinos recortados coinciden con categorías distintas, **se aborta toda
la migración**. El error enumera solo `*1234` e ids de reglas y categorías,
nunca el número completo. Con la versión anterior todavía en ejecución,
revisa esas reglas en «Categorías», decide la categoría correcta y elimina
o modifica la regla contradictoria. Reintenta la actualización con un
respaldo nuevo; la migración no decide por ti.

**Volver atrás de la 0009 exige restaurar el respaldo previo**, siguiendo
«Restaurar un respaldo» y el código anterior correspondiente. `--bajar-a
0008` se niega sin tocar nada: los dígitos eliminados nunca se guardan para
deshacer. Esta negativa también impide bajar hasta revisiones más antiguas.
Los respaldos anteriores sí contienen destinos originales: conserva sus
permisos y no los compartas ni los subas al repositorio.
La migración activa `secure_delete` solo en su conexión SQLite para limpiar
celdas liberadas durante el recorte. No certifica borrado de WAL, journals,
respaldos anteriores ni otras copias del archivo.

##### Conciliación en seco (validar el motor con tu Excel real)

Corre el motor con tu reporte real del banco y tu base real **sin guardar
nada** (la base se abre en solo lectura) y muestra **solo conteos**: cuántas
filas ya estaban, cuántas faltaban, cuántas se preguntarían y cuántos
movimientos del correo no están en el banco. Nunca montos, nombres, fechas ni
números de cuenta, así que puedes compartir la salida.

1. En la Sucursal Virtual, "Descargar movimientos" en Excel.
2. Copia el archivo a la VM con el nombre `Movimientos.xlsx`, en tu carpeta
   de usuario (por ejemplo, desde tu computador:
   `scp Movimientos.xlsx ubuntu@tu-ip:~/`, o subiéndolo en Cloud Shell y
   luego con `scp`).
3. En la VM, este comando de una línea (después de desplegar esta versión y
   migrar); el archivo se lee por la entrada estándar y se borra al final:

```bash
# En la VM
sudo systemd-run --wait --pipe --quiet -p User=finanzas -p Group=finanzas -p EnvironmentFile=/etc/finanzas/finanzas.env -p WorkingDirectory=/opt/finanzas -p Environment=PYTHONDONTWRITEBYTECODE=1 -p ProtectSystem=strict -p ReadOnlyPaths=/var/lib/finanzas -p ProtectHome=true -p PrivateTmp=true -p NoNewPrivileges=true /opt/finanzas/.venv/bin/python -m finanzas.conciliacion_en_seco - < ~/Movimientos.xlsx; rm -f ~/Movimientos.xlsx
```

Cómo leerlo:

- `Resumen: N ya estaban, N faltaban, N para preguntar, N no están en el banco.`
  Lo normal: casi todo lo que llegó por correo sale como "ya estaban"; "faltaban"
  son los cobros sin aviso (Transmilenio, intereses, 4x1000, cuota de manejo);
  "para preguntar", pocos o ninguno.
- "no están en el banco" son movimientos del correo, dentro de las fechas del
  reporte, que el banco no trae: búscalos en la app. El primer día del reporte
  nunca cuenta, tenga las filas que tenga: el banco corta las descargas en un
  tope que no se conoce, y ese día puede venir incompleto.
- "anteriores a tu fecha de inicio" no se importarían (se podrán agregar con
  "Extender historial", ítem 31).
- "Referencia sin formato" son filas cuyo destino no es un número de celular o
  cuenta; entrarían sin destino.
- Si algo no te cuadra (por ejemplo, muchas preguntas o muchos "no están en el
  banco"), **no actives la importación**: comparte la salida con el equipo.

El Excel nunca se guarda: el comando lo lee de la entrada estándar y el `rm`
del final lo borra de tu carpeta. Si el comando no llega al `rm` (por ejemplo,
cierras la terminal), bórralo a mano con `rm -f ~/Movimientos.xlsx`. También se
puede correr antes de desplegar, con el código nuevo en una carpeta aparte
(receta de "Prueba en seco antes de desplegar un cambio del lector", arriba,
cambiando el módulo por `finanzas.conciliacion_en_seco - < ~/Movimientos.xlsx`):
funciona con la base todavía en la 0007.

#### Desplegar el ítem 27 (retiros, pagos QR y pagos PSE)

Esta versión lee tres avisos nuevos y empieza a consultar la segunda dirección
del banco (`alertasynotificaciones@ayn.notificacionesbancolombia.com`, la de
los pagos por PSE). Además de los pasos de arriba (la migración 0006 crea las
categorías "Retiro a efectivo" y "Pago de tarjeta"):

**A. Antes de arrancar (entre los pasos 4 y 5): prueba en seco de `ayn.`.**
Comprueba que los correos de la segunda dirección pasan la verificación de
remitente y DMARC. No escribe nada y solo muestra conteos y fechas. Como el
código nuevo ya está en `/opt/finanzas`, basta con `systemd-run` (las mismas
protecciones que la unidad `finanzas-prueba-en-seco`):

```bash
# En la VM
sudo systemd-run --wait --pipe --quiet \
  -p User=finanzas -p Group=finanzas \
  -p EnvironmentFile=/etc/finanzas/finanzas.env \
  -p WorkingDirectory=/opt/finanzas \
  -p Environment=PYTHONDONTWRITEBYTECODE=1 \
  -p ProtectSystem=strict -p ReadOnlyPaths=/var/lib/finanzas \
  -p ProtectHome=true -p PrivateTmp=true -p NoNewPrivileges=true \
  /opt/finanzas/.venv/bin/python -m finanzas.prueba_en_seco --ayn
```

(Si quieres hacerla **antes** de actualizar, usa la receta de la copia aparte de
arriba con `--ayn` en lugar de `--incluir-no-reconocidos --mostrar-previo`.)

Cómo leerlo:

- `pasan remitente y DMARC` debería ser el total, y la última línea, "Todos
  los correos de ayn. pasan remitente y DMARC.". `se leerían como aviso` dice
  cuántos y de qué tipo (los PSE salen como `compra`).
- Si sale "OJO: hay correos de ayn. rechazados", **no arranques**: vuelve atrás
  ("Volver atrás", abajo) y avisa al equipo con los conteos y el motivo
  (`remitente`, `encabezado_invalido` o `sin_pass_alineado`). No se relaja la
  verificación: se pide el encabezado de uno de esos correos anonimizado.
- Los que salen `no reconocido` son correos de `ayn.` que no son un aviso
  conocido (por ejemplo, de otro tipo): quedarán como no reconocidos, como
  siempre. Si son muchos o eran pagos PSE, avisa con sus fechas.

Si quieres ver también cómo se leerían los retiros y pagos QR que hoy están
como no reconocidos, corre la unidad normal: `sudo systemctl start
finanzas-prueba-en-seco.service` y `journalctl -u finanzas-prueba-en-seco -n 60
--no-pager` (en `no reconocido guardado`, deberían pasar a `aviso válido`).

**B. Después de arrancar (paso 5): leer `ayn.` desde el inicio y reprocesar
los no reconocidos.**

1. **Leer `ayn.` desde la fecha de inicio.** No hace falta nada especial: cada
   sincronización pide a Gmail los correos de las dos direcciones **desde la
   fecha de inicio** y salta los que ya están registrados (por su id de Gmail,
   que es único en la base). La primera sincronización tras desplegar lee
   todos los correos de `ayn.` desde la fecha de inicio, y las siguientes no
   los repiten. Lánzala ya, sin esperar al temporizador:

   ```bash
   # En la VM
   sudo systemctl start finanzas-sync.service
   journalctl -u finanzas-sync -n 5 --no-pager
   ```

   La última línea dice cuántos movimientos nuevos entraron (los pagos PSE),
   cuántos no se reconocieron y cuántos se rechazaron. Si la repites, sale
   `0 nuevos`.

2. **Reprocesar los retiros y pagos QR que quedaron como no reconocidos**
   (ítem 19). En la app, abre `https://tu-subdominio.duckdns.org/app/no-reconocidos`
   y pulsa **"Volver a procesar todos"**. La app vuelve a descargar cada uno
   (solo lectura), le aplica la misma verificación de remitente y DMARC y el
   lector nuevo, y dice cuántos movimientos se crearon y cuántos siguen sin
   reconocerse (esos se quedan en la lista). Reprocesar dos veces no duplica
   nada. (Es el mismo `POST /api/no-reconocidos/reprocesar` de la API; no
   borres filas de `correos_no_reconocidos` a mano.)

**C. Validar.** En la app, revisa septiembre: cada retiro, pago QR y pago PSE
debe aparecer **una sola vez**, los retiros con la categoría "Retiro a
efectivo". Los pagos PSE y QR llegan sin categoría (o con la de una regla): el
pago de una tarjeta de crédito se categoriza como "Pago de tarjeta" y conviene
recordarlo como regla (por la empresa). Si algo aparece dos veces o falta,
avisa con la fecha.

> **Ojo con los pagos QR:** como el aviso no dice a quién se paga, **todos**
> comparten la descripción "Pago por código QR". Una regla por texto sobre
> esa descripción los categoriza a todos igual (el mercado, el almuerzo y el
> taxi quedarían en la misma categoría). Por ahora, categorízalos uno a uno
> sin "Recordar", o crea reglas **por monto** (ítem 17, migración 0007):
> "transferencia de $3.200" alcanza a todos los pagos QR de ese monto.

**Volver atrás de la 0006.** La migración se deshace con `--bajar-a 0005`
("Volver atrás", abajo) solo si ningún movimiento ni regla usa "Retiro a
efectivo" ni "Pago de tarjeta"; si ya se usan, se niega sin tocar nada y hay que
restaurar el respaldo previo a la migración.

#### Desplegar el ítem 20 (retiro de la v1)

Esta versión **retira la interfaz v1** (plantillas y `/static`): la única
interfaz es la app en `/app/`. `/`, `/login`, `/saldo`, `/sin-categorizar` y
`/reglas` redirigen a `/app/...`, y el login es `POST /api/sesion` desde la
pantalla Entrar. No hay migración de base, pero el Caddyfile cambió (solo
cachea `/app/assets/*`) y `requirements.txt` ya no trae `jinja2` ni
`python-multipart`. Todos los comandos son **en la VM**, de uno en uno.

1. Respaldo previo (D26), aunque no haya migración. Comprueba que quedó el
   archivo de hoy en `/var/backups/finanzas`:

   ```bash
   # En la VM
   sudo systemctl start finanzas-respaldo.service && sudo ls -l /var/backups/finanzas | tail -3
   ```

2. Traer el código nuevo:

   ```bash
   # En la VM
   cd /opt/finanzas && sudo git pull --ff-only
   ```

3. Dependencias de Python y paquete local:

   ```bash
   # En la VM
   sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/backend/requirements.txt -e /opt/finanzas
   ```

4. Compilar el frontend (13.2 y 6.1). **Importante:** sin `frontend/dist` la
   app no abre y ya no hay una v1 de respaldo. Si `npm run build` falla, no
   sigas: ve a "Volver atrás de la v1" más abajo.

   ```bash
   # En la VM
   cd /opt/finanzas/frontend && sudo env PATH=/opt/node/bin:/usr/bin:/bin npm ci --ignore-scripts && sudo env PATH=/opt/node/bin:/usr/bin:/bin npm run build; cd /opt/finanzas
   ```

   Debe terminar con `✓ built in …`.

5. Copiar el Caddyfile y recargar Caddy (como en 9.2; el dominio ya está en el
   override de systemd, no se toca):

   ```bash
   # En la VM
   sudo cp /opt/finanzas/deploy/caddy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy && sudo systemctl status caddy --no-pager
   ```

6. Reiniciar el servicio:

   ```bash
   # En la VM
   sudo systemctl restart finanzas.service && sudo systemctl status finanzas.service --no-pager
   ```

7. Verificar. Debe terminar con "Todo en orden." (ver el paso 12 para lo que
   comprueba):

   ```bash
   # En la VM
   sudo bash /opt/finanzas/deploy/verificar.sh tu-subdominio.duckdns.org
   ```

   Después abre `https://tu-subdominio.duckdns.org/` en el celular y en el
   computador: debe llevarte a `/app/` y mostrar la pantalla "Entrar".

**Volver atrás de la v1.** No hay migración que deshacer: la base no cambió y
no hay que restaurar nada. Se vuelve al commit anterior y se repiten la
compilación, Caddy y el reinicio, de uno en uno (cambia `1a2b3c4` por el commit
anterior a la actualización, que ves con el primer comando):

```bash
# En la VM
sudo git -C /opt/finanzas log --oneline -5                    # busca el commit anterior a la actualización
sudo git -C /opt/finanzas checkout 1a2b3c4                    # cámbialo por ese commit
if [ -f /opt/finanzas/backend/requirements.txt ]; then sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/backend/requirements.txt -e /opt/finanzas; else sudo /opt/finanzas/.venv/bin/pip uninstall -y finanzas-personales && sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/requirements.txt; fi
cd /opt/finanzas/frontend && sudo env PATH=/opt/node/bin:/usr/bin:/bin npm ci --ignore-scripts && sudo env PATH=/opt/node/bin:/usr/bin:/bin npm run build; cd /opt/finanzas
sudo cp /opt/finanzas/deploy/caddy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
sudo systemctl restart finanzas.service
```

Cuando la versión nueva esté corregida, vuelve a `main`
(`sudo git -C /opt/finanzas checkout main`) y repite estos pasos.

#### Desplegar el ítem 17 (reglas con condiciones combinables)

La migración 0007 reconstruye la tabla `reglas` (texto opcional y monto exacto
opcional) y conserva intactas las reglas que ya hay. **Antes de migrar, haz el
respaldo previo** (D26): `finanzas-migrar` lo hace solo, pero comprueba que
quedó el archivo `finanzas-antes-de-migrar-<revisión>-*.db` (`0006`, o `0005` si el ítem 27 se despliega a la vez) en `/var/backups/finanzas`
antes de arrancar la app.

**Volver atrás de la 0007.** Se deshace con `--bajar-a 0006` ("Volver atrás",
abajo) solo si no hay reglas con monto ni reglas sin texto (la 0006 no puede
guardarlas); si las hay, se niega sin tocar nada: bórralas desde la app o
restaura el respaldo previo a la migración.

**Qué hace `finanzas-migrar`** (`python -m finanzas.migrar`, ítem 22). La
estructura de la base (tablas, columnas) cambia solo con migraciones
versionadas que vienen con el código. La app y la sincronización **no**
cambian la base por su cuenta: si falta una migración, no arrancan y su
registro dice "Aplica las migraciones con: python -m finanzas.migrar". El
comando:

1. mira en qué versión está la base, sin cambiar nada;
2. si ya está al día, lo dice ("La base ya está al día (revisión ...). No se
   cambió nada.") y termina: ejecutarlo dos veces no cambia nada;
3. si hay migraciones pendientes, primero hace un respaldo en
   `/var/backups/finanzas/finanzas-antes-de-migrar-<revisión>-AAAAMMDDTHHMMSS.db`
   y, solo si el respaldo salió bien, aplica todas en una sola transacción: o
   quedan todas aplicadas o ninguna.

El registro solo muestra revisiones, nombres de archivo y tamaños; nunca
montos ni movimientos.

#### Primera actualización con migraciones (tu base de la v1)

La base que ya tienes la creó la v1, antes de que existieran las migraciones,
así que no tiene versión. La primera vez que ejecutes el paso 3,
`finanzas-migrar` compara su estructura con la de la v1 y, **si coincide
exactamente**, la marca como revisión `0001` sin tocar tus datos (y luego
aplica las migraciones que vengan después). No tienes que hacer nada
distinto: son los mismos comandos de arriba. En el registro verás, en este
orden:

```
La base es de la v1 (sin versión) y su estructura coincide: se marca como 0001.
Respaldo previo: /var/backups/finanzas/finanzas-antes-de-migrar-v1-AAAAMMDDTHHMMSS.db (... bytes).
Listo: la base está en la revisión ...
```

Si en cambio dice **"La base no tiene versión y su estructura no es la de la
v1 esperada (...). No se cambió nada."**, no sigas: la base quedó intacta y
no hace falta restaurar nada. Vuelve al código anterior y arranca de nuevo la
app y los temporizadores (los paraste en el paso 2). En la VM, de uno en uno:

```bash
# En la VM
sudo git -C /opt/finanzas log --oneline -5                    # busca el commit anterior a la actualización
sudo git -C /opt/finanzas checkout 1a2b3c4                    # cámbialo por ese commit
if [ -f /opt/finanzas/backend/requirements.txt ]; then sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/backend/requirements.txt -e /opt/finanzas; else sudo /opt/finanzas/.venv/bin/pip uninstall -y finanzas-personales && sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/requirements.txt; fi
sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer
```

Y pide ayuda con ese mensaje (solo nombra tablas, no datos).

#### Comprobar la versión de la base

```bash
# En la VM
cd /opt/finanzas && sudo -u finanzas .venv/bin/python -m finanzas.migrar --base /var/lib/finanzas/finanzas.db --comprobar; cd ~
```

Dice "La base está al día (revisión ...)" o qué migraciones faltan. No cambia
nada. `verificar.sh` (paso 12) también lo comprueba.

#### Si la migración falla

La unidad queda en "failed" y la base **como estaba** (todo va en una sola
transacción). Mira `journalctl -u finanzas-migrar -n 20 --no-pager`:

- "el respaldo previo falló": no se migró nada. Revisa que exista
  `/var/backups/finanzas` y que haya espacio (`df -h /var/backups`).
- Cualquier otro error: la versión nueva no arranca con la base sin migrar.
  Vuelve a la versión anterior del código ("Volver atrás", abajo) para seguir
  usando la app mientras se corrige.

#### Volver atrás

Si la versión nueva no funciona bien, primero mira qué hizo la migración
(`journalctl -u finanzas-migrar -n 20 --no-pager`). Hay dos casos.

**Caso 1: solo se marcó como `0001`** (la primera actualización: el registro
dice "se marca como 0001" y termina en "la revisión 0001"). Marcar solo añade
la tabla `alembic_version`; tus tablas y datos son los de la v1 y la v1
funciona igual sobre esa base. **No restaures nada**: así no pierdes lo que
hiciste después. Basta con volver al código anterior, en la VM, de uno en uno:

```bash
# En la VM
sudo systemctl stop finanzas-sync.timer finanzas-respaldo.timer finanzas-sync.service finanzas.service
sudo git -C /opt/finanzas log --oneline -5                    # busca el commit anterior a la actualización
sudo git -C /opt/finanzas checkout 1a2b3c4                    # cámbialo por ese commit
if [ -f /opt/finanzas/backend/requirements.txt ]; then sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/backend/requirements.txt -e /opt/finanzas; else sudo /opt/finanzas/.venv/bin/pip uninstall -y finanzas-personales && sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/requirements.txt; fi
sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer
```

Cuando vuelvas a actualizar, `finanzas-migrar` verá que la base ya está en la
`0001` y seguirá desde ahí.

**Caso 2: se aplicaron migraciones que cambian tablas** (el registro dice
"Migraciones aplicadas: 0002..." o posteriores). El código anterior no sabe
leer la estructura nueva: hay que volver al código anterior **y** restaurar
el respaldo previo a esa migración. Todo en la VM, de uno en uno (cambia el
commit y el nombre del respaldo por los tuyos):

```bash
# En la VM
sudo sh -c 'ls -l /var/backups/finanzas/finanzas-antes-de-migrar-*'   # el más reciente es el de esta actualización
sudo systemctl stop finanzas-sync.timer finanzas-respaldo.timer finanzas-sync.service finanzas.service
sudo git -C /opt/finanzas log --oneline -5                    # busca el commit anterior a la actualización
sudo git -C /opt/finanzas checkout 1a2b3c4                    # cámbialo por ese commit
if [ -f /opt/finanzas/backend/requirements.txt ]; then sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/backend/requirements.txt -e /opt/finanzas; else sudo /opt/finanzas/.venv/bin/pip uninstall -y finanzas-personales && sudo /opt/finanzas/.venv/bin/pip install -r /opt/finanzas/requirements.txt; fi
sudo -u finanzas cp -p /var/lib/finanzas/finanzas.db /var/lib/finanzas/finanzas.db.antes-de-restaurar
sudo rm -f /var/lib/finanzas/finanzas.db-journal
sudo install -o finanzas -g finanzas -m 0600 /var/backups/finanzas/finanzas-antes-de-migrar-0001-20261015T101500.db /var/lib/finanzas/finanzas.db
sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer
sudo systemctl start finanzas-sync.service
```

Aquí **no** se lanza `finanzas-migrar`: el respaldo ya está exactamente en la
versión que espera el código anterior (y si ese código es anterior al ítem
22, la unidad ni siquiera existe en él). Lo que hiciste a mano después de
migrar (ingresos, ajustes, categorías, reglas) hay que repetirlo; los avisos
de Gmail vuelven solos. `finanzas.db.antes-de-restaurar` guarda la base
migrada, por si la necesitas; bórrala cuando ya no.

En los dos casos, cuando la versión nueva esté corregida, vuelve a `main`
(`sudo git -C /opt/finanzas checkout main`) y repite 13.2.

Para deshacer solo las últimas migraciones sin restaurar (por ejemplo, si te
lo piden al revisar un error), existe este comando (cambia `0002` por la revisión a la que quieres volver; también hace un respaldo antes). La última revisión hoy es la `0012`. Bajar deshace, de la más nueva a la más vieja, cada migración posterior a la elegida, y se niega sin tocar nada si alguna perdería datos (por ejemplo, la `0007` si hay reglas con monto o sin texto, o la `0006` si se usan sus categorías): entonces hay que restaurar el respaldo. Desde la `0003`, bajar a la `0002` solo quita la hora de la última sincronización correcta (`ultima_correcta_en`), y a la `0001`, además, la tabla del estado de la sincronización:

```bash
# En la VM
cd /opt/finanzas && sudo -u finanzas .venv/bin/python -m finanzas.migrar --base /var/lib/finanzas/finanzas.db --respaldos /var/backups/finanzas --bajar-a 0002; cd ~
```

Nunca baja de la `0001`: para volver a antes de las migraciones se restaura
el respaldo. Después de bajar, el código nuevo no arranca (exige la última
revisión): úsalo junto con el código que corresponde a esa revisión, con la
app y los temporizadores detenidos como en el caso 2.

#### Respaldos previos a migrar: verlos y borrarlos

Estos respaldos **no** se borran solos (la rotación diaria solo toca los
`finanzas-AAAA-MM-DD.db`). Cada uno ocupa lo mismo que la base.

```bash
# En la VM
sudo sh -c 'ls -lh /var/backups/finanzas/finanzas-antes-de-migrar-*'  # verlos, con tamaño y fecha
df -h /var/backups                                            # espacio libre
sudo rm /var/backups/finanzas/finanzas-antes-de-migrar-v1-20260930T101500.db   # borrar uno (cambia el nombre)
```

Borra solo los que ya no necesites (por ejemplo, los de actualizaciones de
hace meses que funcionaron bien) y conserva siempre el más reciente.

La carpeta `/var/backups/finanzas` solo la puede leer el usuario `finanzas`
(y root): por eso estos comandos llevan `sudo`. Cuando hay un `*`, va dentro
de `sudo sh -c '...'`: si no, tu terminal intenta completar el `*` con tu
usuario, que no puede ver esos nombres, y `ls` dice "No such file or
directory".

### 13.3 Restaurar un respaldo

Los respaldos están en `/var/backups/finanzas/finanzas-AAAA-MM-DD.db` (el de
hoy y los de los 14 días anteriores). Los que se hacen antes de cada migración
están en la misma carpeta, como `finanzas-antes-de-migrar-*.db` (13.2).

```bash
# En la VM (cambia la fecha por la del respaldo que quieres)
sudo ls -l /var/backups/finanzas/
sudo systemctl stop finanzas-sync.timer finanzas-respaldo.timer finanzas-sync.service finanzas.service
sudo -u finanzas cp -p /var/lib/finanzas/finanzas.db /var/lib/finanzas/finanzas.db.antes-de-restaurar
sudo rm -f /var/lib/finanzas/finanzas.db-journal
sudo install -o finanzas -g finanzas -m 0600 \
    /var/backups/finanzas/finanzas-2026-09-28.db /var/lib/finanzas/finanzas.db
sudo systemctl start finanzas-migrar.service
sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer
sudo systemctl start finanzas-sync.service
```

- `finanzas-migrar` pone el respaldo restaurado en la versión que espera el
  código instalado (si ya lo está, no hace nada). Si el código instalado es
  anterior al ítem 22 (no tiene `finanzas-migrar`), omite esa línea.
- Para **volver atrás** después de una actualización (restaurar el respaldo
  previo a una migración junto con el código anterior), no uses este bloque:
  sigue 13.2, "Volver atrás", que trae los comandos completos.
- La copia `finanzas.db.antes-de-restaurar` guarda la base que había, por si
  te equivocas de fecha. Bórrala cuando ya no la necesites.
- Lo que pasó después del respaldo: los avisos de Gmail vuelven solos con la
  sincronización; lo que hiciste a mano (ingresos, ajustes, categorías y
  reglas) después de esa fecha hay que repetirlo.

**Opcional: copiar los respaldos fuera de la VM.** Si Oracle borrara la VM, los
respaldos se irían con ella. Para guardar uno en tu computador:

```bash
# En la VM: deja una copia temporal legible por el usuario ubuntu
sudo install -o ubuntu -g ubuntu -m 0600 /var/backups/finanzas/finanzas-2026-09-29.db ~/respaldo.db
```

```bash
# En tu computador
mkdir -p ~/respaldos-finanzas
chmod 700 ~/respaldos-finanzas
scp -i ~/.ssh/oracle_finanzas ubuntu@203.0.113.10:respaldo.db ~/respaldos-finanzas/finanzas-2026-09-29.db
chmod 600 ~/respaldos-finanzas/finanzas-2026-09-29.db
ssh -i ~/.ssh/oracle_finanzas ubuntu@203.0.113.10 'rm ~/respaldo.db'
```

El respaldo tiene todos tus movimientos: guárdalo en un disco cifrado y nunca
en el repositorio.

### 13.4 Cerrar todas las sesiones

Si pierdes el celular o crees que alguien copió tu sesión: cambiar
`SESSION_SECRET` invalida **todas** las cookies de sesión ya emitidas (D10).
Después tendrás que volver a entrar con la contraseña en cada dispositivo.
Vale también para la app instalada en el celular (11.1): usa la misma cookie y
no guarda tus datos, así que sin sesión no muestra nada.

```bash
# En la VM
sudo python3 - <<'EOF'
import re, secrets
ruta = "/etc/finanzas/finanzas.env"
texto = open(ruta).read()
nuevo, n = re.subn(r"(?m)^SESSION_SECRET=.*$", "SESSION_SECRET=" + secrets.token_urlsafe(48), texto)
if n != 1:
    raise SystemExit("No encontré exactamente una línea SESSION_SECRET= en " + ruta)
with open(ruta, "w") as archivo:  # "w" conserva el dueño y los permisos (root:root 600)
    archivo.write(nuevo)
print("SESSION_SECRET cambiado.")
EOF
sudo systemctl restart finanzas
```

La clave nueva se genera y se escribe sin mostrarse. Si además crees que alguien
conoce tu contraseña, cámbiala (13.5).

### 13.5 Cambiar la contraseña

Igual que en 7.1, en partes: la que pide la contraseña se escribe a mano,
porque lo que pegues después se tomaría como la contraseña.

**Parte A: a mano.** Pide la contraseña nueva dos veces.

```bash
# En la VM (parte A: a mano)
cd /opt/finanzas
HASH=$(.venv/bin/python -m finanzas.seguridad)
echo "${HASH:0:7}"
```

Debe mostrar `scrypt:`. Si muestra una línea vacía, repite la línea `HASH=...`.

**Parte B: se puede pegar.** Cambia solo la línea `APP_PASSWORD_HASH` y
reinicia la app.

```bash
# En la VM (parte B: se puede pegar)
if [[ $HASH == scrypt:* ]]; then
sudo python3 - <<EOF
import re
ruta = "/etc/finanzas/finanzas.env"
texto = open(ruta).read()
nuevo, n = re.subn(r"(?m)^APP_PASSWORD_HASH=.*$", "APP_PASSWORD_HASH=$HASH", texto)
if n != 1:
    raise SystemExit("No encontré exactamente una línea APP_PASSWORD_HASH= en " + ruta)
with open(ruta, "w") as archivo:
    archivo.write(nuevo)
print("Contraseña cambiada.")
EOF
sudo systemctl restart finanzas
else
echo "ERROR: no se generó el hash; la contraseña no cambió. Repite la parte A."
fi
```

**Parte C: a mano.**

```bash
# En la VM (parte C: a mano)
unset HASH
cd ~
sudo grep -c '^APP_PASSWORD_HASH=scrypt:' /etc/finanzas/finanzas.env
```

Debe mostrar `1`.

Si las contraseñas no coinciden o son muy cortas, la parte B no toca
`finanzas.env` (así nunca queda un `APP_PASSWORD_HASH=` vacío). El archivo
conserva su dueño y sus permisos (`root:root 600`).

Cambiar la contraseña **no** cierra las sesiones abiertas; para eso, 13.4.

### 13.6 Revocar el acceso a Gmail

1. En <https://myaccount.google.com/permissions> quita el acceso a la app (paso 9
   de la guía docs/GMAIL.md). Desde ese momento el token no sirve.
2. Borra el token de la VM:

   ```bash
   # En la VM
   sudo rm /var/lib/finanzas/gmail/token.json
   ```

La app sigue funcionando, pero "Sincronizar ahora" avisará que falta la
autorización y `finanzas-sync` terminará con código 2. Para volver a
conectar, repite el paso 8.

### 13.7 Cambiar el intervalo de sincronización

Por defecto es cada 6 horas. Para cambiarlo sin tocar el archivo original:

```bash
# En la VM
sudo systemctl edit finanzas-sync.timer
```

Se abre un editor. Escribe, en la zona indicada:

```
[Timer]
OnCalendar=
OnCalendar=*-*-* 00/3:00:00
```

La línea `OnCalendar=` vacía borra el horario anterior. Ejemplos:
`*-*-* 00/3:00:00` cada 3 horas, `*-*-* 00/12:00:00` cada 12 horas,
`*-*-* 08,20:00:00` a las 8:00 y a las 20:00. Guarda y aplica:

```bash
# En la VM
sudo systemctl restart finanzas-sync.timer
systemctl list-timers finanzas-sync.timer
```

Para volver al original: `sudo systemctl revert finanzas-sync.timer`.

---

## 14. Solución de problemas

**Todos los formularios (empezando por el login) responden 403.**
La app compara el `Origin` del navegador con el `Host` de la petición. Si
Caddy reescribe `Host`, no coinciden. Revisa que `/etc/caddy/Caddyfile` sea
igual a `deploy/caddy/Caddyfile` y que dentro de `reverse_proxy` no haya ningún
`header_up` que cambie el `Host`. Aplica con `sudo systemctl reload caddy`.
También pasa si entras por la IP en lugar del subdominio: usa siempre
`https://tu-subdominio.duckdns.org`.

**El navegador dice que el certificado no es válido o no carga nada.**
Caddy no pudo obtener el certificado. Mira `journalctl -u caddy -n 100 --no-pager`.
Casi siempre es una de estas:
- Los puertos 80 o 443 están cerrados: revisa la Security List (4.1) **y**
  `iptables` (4.2). Los dos.
- El subdominio no apunta a la IP de la VM: `nslookup tu-subdominio.duckdns.org`
  en tu computador debe mostrar la IP reservada. Si no, revisa DuckDNS (paso 3)
  y `journalctl -u duckdns -n 20`.
- `DOMINIO` no está definido o tiene un error: `systemctl show caddy -p Environment`.
Let's Encrypt limita los intentos fallidos; tras corregir, espera unos minutos.

**El registro de Caddy tiene "error" al principio, o 502.**
No todo lo que dice "error" es un fallo:
- `"creating new account because no account ... is known"` y
  `"error":"open .../default.json"` en las primeras líneas son de nivel `info`
  y normales: Caddy crea su cuenta de Let's Encrypt la primera vez.
- Los 502 con `connection refused` hacia `127.0.0.1:8000` antes del paso 10
  son normales: la app todavía no está encendida. Si siguen después del paso
  10, mira `journalctl -u finanzas -n 50 --no-pager`.
- Las visitas de robots desconocidos poco después de emitir el certificado
  también son normales (ver 9.2).
Lo que importa es que aparezca `certificate obtained successfully`:
`journalctl -u caddy --no-pager | grep -i "certificate obtained successfully"`.

**`finanzas-sync` falla y el registro dice `ErrorAutorizacionGmail` (o termina con código 2).**
El token de Gmail falta, no se puede leer o fue revocado (también pasa si
cambiaste la contraseña de Gmail o si pasaron 6 meses sin usarlo). Revisa los
permisos del token (`sudo stat -c '%U:%G %a' /var/lib/finanzas/gmail/token.json`
→ `finanzas:finanzas 600`) y la ruta en `GMAIL_TOKEN`. Si todo está bien,
autoriza de nuevo (paso 8). El código 2 también sale si falta la fecha de
inicio (paso 11.3).

**"database is locked".**
Dos procesos quisieron escribir la base a la vez (la app, la sincronización o
el respaldo) y uno esperó más de la cuenta. Normalmente se arregla solo en la
siguiente sincronización. Si se repite, comprueba que no tengas abierta una
sesión de `sqlite3` sobre `/var/lib/finanzas/finanzas.db` y que no haya dos
sincronizaciones al mismo tiempo (`systemctl status finanzas-sync`). Nunca
borres el archivo `finanzas.db-journal` con la app encendida.

**La app no arranca.**
`journalctl -u finanzas -n 50 --no-pager`. Si dice "Falta la variable de
entorno obligatoria" o "APP_PASSWORD_HASH no tiene el formato esperado",
revisa `/etc/finanzas/finanzas.env` (paso 7.1). El mensaje nombra la variable,
nunca su valor. Si dice "La base de datos no está en la última versión de su
estructura", falta migrar: mientras tanto `finanzas.service` lo reintenta
cada 5 segundos (`Restart=on-failure`) y el registro repite ese mensaje; no
es grave, pero no se arreglará solo. Lanza
`sudo systemctl start finanzas-migrar.service` (detiene la app mientras
migra), lee su registro (`journalctl -u finanzas-migrar -n 20 --no-pager`) y,
si terminó bien, arranca de nuevo con
`sudo systemctl start finanzas.service finanzas-sync.timer finanzas-respaldo.timer`.
Si la migración falla, sigue 13.2 ("Si la migración falla"). Lo mismo si
`finanzas-sync` termina con código 2 y ese mensaje.

**No puedo entrar por SSH.**
Comprueba la IP (la reservada del paso 2, que no es la del principio), la
llave (`-i ~/.ssh/oracle_finanzas` en tu computador o `-i ~/.ssh/finanzas_vm`
en Cloud Shell) y el usuario (`ubuntu`). Si Oracle no aceptó la llave o no
entra nunca, revisa que la pública se pegó en una sola línea y con el espacio
después de `ssh-rsa` o `ssh-ed25519` (paso 1.3). Si cambiaste las reglas de
`iptables` y perdiste el acceso, reinicia la instancia desde la consola de
Oracle (Instances → `finanzas` → Reboot): las reglas que no guardaste con
`netfilter-persistent save` se pierden al reiniciar.
