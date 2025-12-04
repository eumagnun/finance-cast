import logging
import os
import shutil
from google.cloud import texttospeech
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import load_artifacts
from google.cloud import storage
from pydub import AudioSegment
from datetime import datetime

# --- 1. CONFIGURAÇÕES PRINCIPAIS ---

# ID do seu projeto Google Cloud
PROJECT_ID = "project-poc-purple"  # Altere para o seu Project ID
BUCKET_NAME = "demo-podcast"  # <--- DEFINA SEU BUCKET AQUI
PASTA_NO_BUCKET = "podcasts_gerados"     # Pasta dentro do bucket (opcional)

# Configurações do Text-to-Speech
MODELO_TTS = "gemini-2.5-pro-tts"
CODIGO_IDIOMA = "pt-br"

# Defina os participantes e suas vozes
LOCUTOR_1 = {"alias": "Assessor", "voz": "Algenib"}
LOCUTOR_2 = {"alias": "Assessor", "voz": "Algenib"} # Mesma voz para monólogo

# Configurações de arquivos
PASTA_SAIDA = ".podcast_segmentos"
ARQUIVO_FINAL = "podcast_final.wav"

# Limite de caracteres por chamada de API (o limite oficial é 5000)
LIMITE_CARACTERES_POR_CHAMADA = 4500

# --- 1a. CONFIGURAÇÕES DE CUSTO ---
PRECO_POR_MILHAO_TEXT_TOKENS = 1.00
PRECO_POR_MILHAO_AUDIO_TOKENS = 20.00
AUDIO_TOKENS_POR_SEGUNDO = 25
# Suposição: 1 token de texto ~= 4 caracteres.
# Esta é uma aproximação comum para modelos de linguagem.
CARACTERES_POR_TEXT_TOKEN = 4

def segmentar_texto(texto, limite):
    if len(texto) <= limite:
        return [texto]
    segmentos = []
    while len(texto) > limite:
        ponto_de_corte = texto.rfind('.', 0, limite)
        if ponto_de_corte == -1: ponto_de_corte = texto.rfind('?', 0, limite)
        if ponto_de_corte == -1: ponto_de_corte = texto.rfind('!', 0, limite)
        if ponto_de_corte == -1: ponto_de_corte = texto.rfind(' ', 0, limite)
        if ponto_de_corte == -1: ponto_de_corte = limite
        segmentos.append(texto[:ponto_de_corte + 1])
        texto = texto[ponto_de_corte + 1:].strip()
    if texto:
        segmentos.append(texto)
    return segmentos

def gerar_audio(client, locutor, texto, indice):
    try:
        nome_arquivo = os.path.join(PASTA_SAIDA, f"segmento_{indice:03d}.wav")
        print(f"Gerando áudio para o segmento {indice} com a voz '{locutor['voz']}'...")
        synthesis_input = texttospeech.SynthesisInput(text=texto)
        voice = texttospeech.VoiceSelectionParams(
            language_code=CODIGO_IDIOMA, name=locutor["voz"], model_name=MODELO_TTS
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16
        )
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        with open(nome_arquivo, "wb") as out:
            out.write(response.audio_content)
        print(f"-> Áudio salvo em: {nome_arquivo}")
        return nome_arquivo
    except Exception as e:
        print(f"Erro ao gerar áudio para o segmento {indice}: {e}")
        return None

def concatenar_audios(lista_de_arquivos, arquivo_final):
    if not lista_de_arquivos:
        print("Nenhum arquivo de áudio para concatenar.")
        return
    print("\nIniciando a concatenação dos áudios...")
    audio_combinado = AudioSegment.from_wav(lista_de_arquivos[0])
    for nome_arquivo in lista_de_arquivos[1:]:
        proximo_audio = AudioSegment.from_wav(nome_arquivo)
        audio_combinado += proximo_audio
    audio_combinado.export(arquivo_final, format="wav")
    print(f"\n✅ Áudio concatenado localmente em '{arquivo_final}' (pronto para upload)")
    return True

def enviar_para_bucket(arquivo_local, bucket_name, destino_blob):
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destino_blob)
        
        print(f"Enviando '{arquivo_local}' para 'gs://{bucket_name}/{destino_blob}'...")
        blob.upload_from_filename(arquivo_local)

        #blob.make_public() 
        
        url_publica = blob.public_url
        
        print(f"✅ Upload concluído! URL: {url_publica}")
        return url_publica
    except Exception as e:
        print(f"❌ Erro ao enviar para o bucket: {e}")
        return False

def limpar_arquivos_temporarios():
    """Remove a pasta de segmentos e o arquivo final local."""
    print("\nIniciando limpeza de arquivos temporários...")
    
    # 1. Remove a pasta de segmentos e todo seu conteúdo
    if os.path.exists(PASTA_SAIDA):
        shutil.rmtree(PASTA_SAIDA)
        print(f"🗑️  Pasta '{PASTA_SAIDA}' removida.")
    
    # 2. Remove o arquivo final local (pois já está no bucket)
    if os.path.exists(ARQUIVO_FINAL):
        os.remove(ARQUIVO_FINAL)
        print(f"🗑️  Arquivo local '{ARQUIVO_FINAL}' removido.")

def gerar_podcast(TEXTO_ENTRADA):
    os.environ["GCLOUD_PROJECT"] = PROJECT_ID
    client = texttospeech.TextToSpeechClient()
    if not os.path.exists(PASTA_SAIDA):
        os.makedirs(PASTA_SAIDA)
        print(f"Pasta '{PASTA_SAIDA}' criada.")

    print("Processando texto de entrada...")
    paragrafos = [p.strip() for p in TEXTO_ENTRADA.strip().split('\n') if p.strip()]
    roteiro = []
    for i, paragrafo in enumerate(paragrafos):
        locutor_atual = LOCUTOR_1 if i % 2 == 0 else LOCUTOR_2
        roteiro.append((locutor_atual, paragrafo))

    turnos_processados = []
    for locutor, texto in roteiro:
        segmentos = segmentar_texto(texto, LIMITE_CARACTERES_POR_CHAMADA)
        for segmento in segmentos:
            turnos_processados.append((locutor, segmento))

    arquivos_de_audio_gerados = []
    total_segmentos = len(turnos_processados)
    print(f"\nO roteiro foi dividido em {total_segmentos} segmentos para geração de áudio.")
    
    for i, (locutor, texto_segmentado) in enumerate(turnos_processados):
        arquivo = gerar_audio(client, locutor, texto_segmentado, i + 1)
        if arquivo:
            arquivos_de_audio_gerados.append(arquivo)

    resultado_final = "Falha ao gerar o podcast."

    if len(arquivos_de_audio_gerados) == total_segmentos:
        # 1. Concatena (Salva localmente como 'podcast_final.wav')
        sucesso_concat = concatenar_audios(arquivos_de_audio_gerados, ARQUIVO_FINAL)
        
        # 2. Faz Upload com nome modificado
        if sucesso_concat:
            # --- MODIFICAÇÃO PARA YYYYMMDDSS ---
            # Gera o sufixo: Ano Mês Dia Segundos
            timestamp = datetime.now().strftime("%Y%m%d%S")
            
            # Separa o nome da extensão (.wav)
            nome_base, extensao = os.path.splitext(ARQUIVO_FINAL)
            
            # Cria o novo nome para o Bucket: podcast_final_2023102745.wav
            nome_arquivo_bucket = f"{nome_base}_{timestamp}{extensao}"
            caminho_blob = f"{PASTA_NO_BUCKET}/{nome_arquivo_bucket}"
            
            # Envia usando o novo nome de destino, mas lendo o arquivo local original
            url_gerada = enviar_para_bucket(ARQUIVO_FINAL, BUCKET_NAME, caminho_blob)
            
            if url_gerada:
                limpar_arquivos_temporarios()
                resultado_final = f"Podcast criado com sucesso. Disponível em: {url_gerada}"
            else:
                resultado_final = "Podcast criado localmente, mas falha no upload para o Bucket."
        else:
            resultado_final = "Falha na concatenação dos áudios."
    else:
        resultado_final = "A geração foi cancelada devido a erros em segmentos de áudio."
        print("\n❌ Cancelado.")

    return resultado_final

gerador_resumo_agent = LlmAgent(
    name="gerador_resumo_agent",
    model="gemini-2.5-flash",
    instruction="""
        Você é um especialista financeiro 
        Gere um resumo com base no conteudo disponibilizado.
        O mesmo representa fatos ocorridos sobre assets contidas na carteira de investimentos de um investidor do Banco do Brasil.
        O resumo deve ser gerado como um podcast de uma pessoa falando com o cliente chamado Daniel.
        O resumo deve ser composto de saudação seguido de 3 fatos mais relevantes
        """,
    tools=[load_artifacts],
)

gerador_podcast_agent = LlmAgent(
    name="gerador_podcast_agent",
    model="gemini-2.5-flash",
    instruction="""
        Você é um especialista em criar podcast.
        Você espera que te encaminhem um roteiro para o podcast.
        Com esse roteiro em mãos, você usará a ferramenta gerar_podcast.
        IMPORTANTE: Ao final, você DEVE responder ao usuário com a URL retornada pela ferramenta.
        """,
    tools=[gerar_podcast],
)

pipeline_agent = SequentialAgent(
    name="pipeline_agent",
    sub_agents=[gerador_resumo_agent, gerador_podcast_agent],
    description="Executes a sequence of code writing, reviewing, and refactoring.",
    # The agents will run in the order provided: Writer -> Reviewer -> Refactorer
)

root_agent = pipeline_agent

logging.basicConfig(level=logging.INFO)