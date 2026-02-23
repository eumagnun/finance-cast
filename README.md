#google-utilities

## IMPORTANTE: software apenas para fins de demonstração


 - Clonar esse repo
 ````
git clone xxxxxxx
 ````
 - Criar ambiente virtual:
```bash
python -m venv .venv
```
 - Ativar ambiente virtual:

Linux
````bash
source .venv/bin/activate
````
Windows
 ````bash
.venv\Scripts\activate
 ````

 - Instalar dependências:
 ```bash
pip install -r requirements.txt
 ```
 - Definir variáveis de ambiente via .env
 - required:
 ```
  sudo apt update
  sudo apt install ffmpeg
 ```
 - Executar app:
 ```
xxxxxxxxx
 ```
Caso queira gerar uma imagem para implantação no Cloud Run:

 - Gerar imagem:
 ````
docker build -t us-central1-docker.pkg.dev/project-poc-purple/demos/finance-cast.
 ````
 - Enviar imagem para o Registry:
 ````
docker push us-central1-docker.pkg.dev/project-poc-purple/demos/finance-cast
 ````

