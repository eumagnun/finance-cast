import logging
import os
from google.cloud import texttospeech
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import load_artifacts
from pydub import AudioSegment

# --- 1. CONFIGURAÇÕES PRINCIPAIS ---

# ID do seu projeto Google Cloud
PROJECT_ID = "project-poc-purple"  # Altere para o seu Project ID

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
    print(f"\n✅ Sucesso! O podcast foi montado e salvo como '{arquivo_final}'")

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

    if len(arquivos_de_audio_gerados) == total_segmentos:
        concatenar_audios(arquivos_de_audio_gerados, ARQUIVO_FINAL)
    else:
        print("\n❌ A concatenação foi cancelada devido a erros na geração de um ou mais segmentos.")

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
    name="advogado_agent",
    model="gemini-2.5-flash",
    instruction="""
    Você é um especialista em criar podcast.
    Você espera que te encaminhem um roteiro para o podcast.
    Com esse roteiro em mão você sua gerrament
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