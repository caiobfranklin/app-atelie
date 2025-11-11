# --- Importações ---
import streamlit as st
from datetime import date
import json
from fpdf import FPDF
import os 
import uuid
from PIL import Image
from supabase import create_client, Client
import io

# --- Parte 1: Ligação ao SUPABASE (com Segredos) ---
try:
    SUPABASE_URL = st.secrets["supabase_url"]
    SUPABASE_KEY = st.secrets["supabase_key"]
except KeyError:
    st.error("ERRO: As 'supabase_url' e 'supabase_key' não foram configuradas nos segredos do Streamlit.")
    st.stop()
    
NOME_BUCKET_FOTOS = "fotos-pecas"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Erro ao ligar ao Supabase: {e}")
    st.stop()

# --- Parte 2: Definição das Constantes ---
PRECO_BISCOITO_POR_KG = 13.0
PRECO_ESMALTE_POR_CM3 = 0.013
PRECO_ARGILA_ATELIE_KG = 7.0

# --- Parte 3: A "Classe" Peca (Idêntica) ---
class Peca:
    # (Esta classe é 100% idêntica à versão 8.3)
    def __init__(self, data_producao, nome_pessoa, tipo_peca, peso_kg, altura_cm, largura_cm, profundidade_cm, 
                 tipo_argila='nenhuma', preco_argila_propria=0.0, 
                 image_path=None, peca_id=None):
        self.id = peca_id if peca_id else str(uuid.uuid4())
        self.data_producao = data_producao
        self.nome_pessoa = nome_pessoa
        self.tipo_peca = tipo_peca
        self.peso_kg = float(peso_kg)
        self.altura_cm = float(altura_cm)
        self.largura_cm = float(largura_cm)
        self.profundidade_cm = float(profundidade_cm)
        self.tipo_argila = tipo_argila
        self.preco_argila_propria = float(preco_argila_propria) if self.tipo_argila == 'propria' else 0.0
        self.data_registro = date.today().strftime("%d/%m/%Y")
        self.image_path = image_path
        self.custo_argila = 0.0
        self.custo_biscoito = 0.0
        self.custo_esmalte = 0.0
        self.total = 0.0
        self.recalcular_custos() 

    def recalcular_custos(self):
        if self.tipo_argila == 'atelie':
            self.custo_argila = self.peso_kg * PRECO_ARGILA_ATELIE_KG
        elif self.tipo_argila == 'propria':
            self.custo_argila = self.peso_kg * self.preco_argila_propria
        else:
            self.custo_argila = 0.0
        self.custo_biscoito = self.peso_kg * PRECO_BISCOITO_POR_KG
        volume_cm3 = self.altura_cm * self.largura_cm * self.profundidade_cm
        self.custo_esmalte = volume_cm3 * PRECO_ESMALTE_POR_CM3
        self.total = self.custo_biscoito + self.custo_esmalte + self.custo_argila

    def to_dict(self):
        return {
            "id": self.id, "data_producao": self.data_producao, "nome_pessoa": self.nome_pessoa,
            "tipo_peca": self.tipo_peca, "peso_kg": self.peso_kg, "altura_cm": self.altura_cm,
            "largura_cm": self.largura_cm, "profundidade_cm": self.profundidade_cm,
            "tipo_argila": self.tipo_argila, "preco_argila_propria": self.preco_argila_propria,
            "data_registro": self.data_registro, "image_path": self.image_path,
            "custo_argila": self.custo_argila, "custo_biscoito": self.custo_biscoito,
            "custo_esmalte": self.custo_esmalte, "total": self.total
        }

    @classmethod
    def from_dict(cls, data_dict):
        peca = cls(
            peca_id=data_dict.get('id'), data_producao=data_dict.get('data_producao'),
            nome_pessoa=data_dict.get('nome_pessoa'), tipo_peca=data_dict.get('tipo_peca'),
            peso_kg=float(data_dict.get('peso_kg', 0)), altura_cm=float(data_dict.get('altura_cm', 0)),
            largura_cm=float(data_dict.get('largura_cm', 0)), profundidade_cm=float(data_dict.get('profundidade_cm', 0)),
            tipo_argila=data_dict.get('tipo_argila', 'nenhuma'), preco_argila_propria=float(data_dict.get('preco_argila_propria', 0)),
            image_path=data_dict.get('image_path')
        )
        peca.custo_argila = float(data_dict.get('custo_argila', 0))
        peca.custo_biscoito = float(data_dict.get('custo_biscoito', 0))
        peca.custo_esmalte = float(data_dict.get('custo_esmalte', 0))
        peca.total = float(data_dict.get('total', 0))
        return peca

# --- Parte 4: Funções de Dados (Idênticas) ---
def carregar_dados():
    try:
        response = supabase.table('pecas').select('*').order('created_at', desc=True).execute()
        dados = response.data
        if dados:
            return [Peca.from_dict(d) for d in dados]
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
    return []

def salvar_nova_peca(nova_peca: Peca, uploaded_file):
    image_db_path = None
    if uploaded_file is not None:
        try:
            extensao = os.path.splitext(uploaded_file.name)[1]
            image_db_path = f"{nova_peca.id}{extensao}" 
            file_bytes = uploaded_file.getvalue()
            supabase.storage.from_(NOME_BUCKET_FOTOS).upload(
                path=image_db_path, file=file_bytes,
                file_options={"content-type": uploaded_file.type, "upsert": "true"}
            )
            nova_peca.image_path = image_db_path
        except Exception as e:
            st.error(f"Erro ao fazer upload da imagem: {e}")
            return False
    try:
        dados_para_salvar = nova_peca.to_dict()
        supabase.table('pecas').insert(dados_para_salvar).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar dados da peça: {e}")
        if image_db_path:
            supabase.storage.from_(NOME_BUCKET_FOTOS).remove([image_db_path])
        return False

def excluir_peca_db(peca: Peca):
    if peca.image_path:
        try:
            supabase.storage.from_(NOME_BUCKET_FOTOS).remove([peca.image_path])
        except Exception as e:
            st.warning(f"Erro ao excluir a foto: {e}")
    try:
        supabase.table('peca').delete().eq('id', peca.id).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao excluir os dados da peça: {e}")
        return False

# --- Parte 5: Funções de Geração (Idênticas) ---
def get_public_url(image_path):
    if not image_path:
        return None
    try:
        return f"{SUPABASE_URL}/storage/v1/object/public/{NOME_BUCKET_FOTOS}/{image_path}"
    except Exception:
        return None

def gerar_relatorio_pdf(lista_de_pecas):
    # (Função idêntica à V8.3)
    if not lista_de_pecas: return None
    custo_geral_total = 0.0
    totais_por_pessoa = {}
    for peca in lista_de_pecas:
        nome, total_peca = peca.nome_pessoa, peca.total
        custo_geral_total += total_peca
        total_anterior_pessoa = totais_por_pessoa.get(nome, 0.0)
        totais_por_pessoa[nome] = total_anterior_pessoa + total_peca
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page(); pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Relatorio de Producao do Atelie', ln=True, align='C'); pdf.ln(5)
    for peca in lista_de_pecas:
        pdf.set_font('Arial', '', 10); image_url = get_public_url(peca.image_path)
        if image_url:
            try:
                y_antes = pdf.get_y(); pdf.image(image_url, x=170, y=y_antes, w=30); pdf.set_auto_page_break(auto=False, margin=0)
            except Exception as e: print(f"Erro ao adicionar imagem URL ao PDF: {e}")
        pdf.set_font('Arial', 'B', 10)
        linha1 = f"Data Prod.: {peca.data_producao} | Pessoa: {peca.nome_pessoa} | Peca: {peca.tipo_peca}"
        pdf.multi_cell(160, 5, linha1.encode('latin-1', 'replace').decode('latin-1'), border=0, ln=True)
        pdf.set_font('Arial', '', 10)
        linha2 = f"  Custos: Biscoito(R$ {peca.custo_biscoito:.2f}), Esmalte(R$ {peca.custo_esmalte:.2f}), Argila(R$ {peca.custo_argila:.2f})"
        pdf.multi_cell(160, 5, linha2.encode('latin-1', 'replace').decode('latin-1'), border=0, ln=True)
        linha3 = f"  >> Total da Peca: R$ {peca.total:.2f}"
        pdf.multi_cell(160, 5, linha3.encode('latin-1', 'replace').decode('latin-1'), border=0, ln=True)
        linha4 = f"  (Registrado em: {peca.data_registro})"
        pdf.multi_cell(160, 5, linha4.encode('latin-1', 'replace').decode('latin-1'), border=0, ln=True)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y()); pdf.ln(3)
    pdf.ln(10); pdf.set_font('Arial', 'B', 12); pdf.cell(0, 5, '--- RESUMO TOTAL ---', ln=True, align='C')
    pdf.set_font('Arial', '', 10); pdf.cell(0, 5, f"Total de pecas: {len(lista_de_pecas)}", ln=True)
    pdf.cell(0, 5, f"CUSTO GERAL TOTAL: R$ {custo_geral_total:.2f}", ln=True); pdf.ln(5)
    pdf.set_font('Arial', 'B', 12); pdf.cell(0, 5, '--- RESUMO POR PESSOA ---', ln=True, align='C')
    pdf.set_font('Arial', '', 10)
    for nome, total_pessoa in totais_por_pessoa.items():
        linha_total_pessoa = f"  {nome}: R$ {total_pessoa:.2f}"
        pdf.cell(0, 5, linha_total_pessoa.encode('latin-1', 'replace').decode('latin-1'), ln=True)
    nome_arquivo_pdf = f"relatorio_atelie_{date.today().strftime('%Y-%m-%d')}.pdf"
    try:
        pdf.output(nome_arquivo_pdf); return nome_arquivo_pdf
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}"); return None

# --- Parte 6: A INTERFACE WEB (Streamlit - ATUALIZADA) ---

st.set_page_config(page_title="Gestão BAL", layout="wide", page_icon="🏺") # <-- Ícone adicionado!

# Título e Logo principal não são mais necessários aqui, vão para a Home
# st.title("🏺 Sistema de Gestão de Custos do Ateliê (v8.5)")

if 'inventario' not in st.session_state:
    with st.spinner("A carregar dados do armazém..."):
        st.session_state.inventario = carregar_dados()

st.sidebar.title("Menu") # <-- Título do menu
pagina = st.sidebar.radio("Navegue por:", 
                         ["Home", "Ver Relatório Completo", "Adicionar Nova Peça", "Excluir Peça"]) # <-- NOVA PÁGINA "Home"

# --- NOVA PÁGINA 1: HOME ---
if pagina == "Home":
    st.title("BAL Cerâmica")
    st.write("Bem-vindo ao sistema de gestão de custos do ateliê.")
    
    # --- COLOQUE O LINK DA SUA LOGO AQUI ---
    # 1. Suba a logo para o bucket 'fotos-pecas'
    # 2. Obtenha a URL pública e cole-a abaixo
    LOGO_URL = "https://jlrzbcighlymiibcvhte.supabase.co/storage/v1/object/public/fotos-pecas/logo-bal.jpg" # <-- SUBSTITUA PELA URL REAL
    
    # Tenta exibir a logo
    if LOGO_URL.startswith("https://"):
        st.image(LOGO_URL, width=300)
    else:
        st.warning("Para exibir a sua logo, por favor, atualize a 'LOGO_URL' no código.")
        
    st.info("Utilize as opções no **Menu** à esquerda para começar.")

# --- PÁGINA 2: VER RELATÓRIO ---
elif pagina == "Ver Relatório Completo":
    st.header("Relatório de Produção")
    
    if st.button("Atualizar Dados (Recarregar do Supabase)"):
        with st.spinner("A carregar dados do armazém..."):
            st.session_state.inventario = carregar_dados()
    
    inventario = st.session_state.inventario
    
    if not inventario:
        st.warning("Nenhuma peça foi adicionada ao inventário ainda.")
    else:
        # (Resto da página de relatório é idêntico à V8.3)
        st.subheader("Filtros do Relatório")
        lista_pessoas = sorted(list(set([p.nome_pessoa for p in inventario if p.nome_pessoa])))
        col1, col2 = st.columns(2)
        filtro_pessoa = col1.multiselect("Filtrar por Pessoa:", options=lista_pessoas)
        filtro_data = col2.text_input("Filtrar por Data de Produção (DD/MM/AAAA):")
        
        lista_para_relatorio = inventario
        if filtro_pessoa:
            lista_para_relatorio = [p for p in lista_para_relatorio if p.nome_pessoa in filtro_pessoa]
        if filtro_data:
            lista_para_relatorio = [p for p in lista_para_relatorio if p.data_producao == filtro_data]

        st.subheader("Exportar Relatório")
        nome_do_pdf = gerar_relatorio_pdf(lista_para_relatorio)
        if nome_do_pdf:
            try:
                with open(nome_do_pdf, "rb") as f:
                    st.download_button(label="Baixar Relatório em PDF", data=f, file_name=nome_do_pdf, mime="application/pdf")
            except FileNotFoundError: st.error("Erro ao ler o ficheiro PDF gerado.")
        st.divider()

        st.subheader(f"Exibindo {len(lista_para_relatorio)} Peças")
        custo_geral_total = 0.0
        totais_por_pessoa = {}
        for peca in lista_para_relatorio:
            nome, total_peca = peca.nome_pessoa, peca.total
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Peça:** {peca.tipo_peca} | **Pessoa:** {nome} | **Data:** {peca.data_producao}")
                    st.write(f"Custos: Biscoito(R$ {peca.custo_biscoito:.2f}), Esmalte(R$ {peca.custo_esmalte:.2f}), Argila(R$ {peca.custo_argila:.2f})")
                    st.subheader(f"Total da Peça: R$ {total_peca:.2f}")
                with col2:
                    image_url = get_public_url(peca.image_path)
                    if image_url: st.image(image_url, width=150)
                    else: st.caption("Sem foto")
            custo_geral_total += total_peca
            total_anterior_pessoa = totais_por_pessoa.get(nome, 0.0)
            totais_por_pessoa[nome] = total_anterior_pessoa + total_peca
        st.divider()
        st.subheader("Resumo Total (do Filtro)")
        col1, col2 = st.columns(2)
        col1.metric(label="Total de Peças na Seleção", value=len(lista_para_relatorio))
        col2.metric(label="Custo Geral desta Seleção", value=f"R$ {custo_geral_total:.2f}")
        st.subheader("Resumo por Pessoa (na Seleção)")
        st.dataframe(totais_por_pessoa)

# --- PÁGINA 3: ADICIONAR NOVA PEÇA ---
elif pagina == "Adicionar Nova Peça":
    st.header("Adicionar Nova Peça")
    
    with st.form(key="nova_peca_form", clear_on_submit=True):
        st.subheader("Dados da Peça")
        nome_pessoa = st.text_input("Quem produziu a peça?")
        tipo_peca = st.text_input("Qual o tipo de peça? (Ex: Copo, Vaso)")
        data_producao = st.text_input("Qual a data de produção? (DD/MM/AAAA)")
        uploaded_file = st.file_uploader("Anexar foto da peça", type=["png", "jpg", "jpeg"])
        st.subheader("Medidas")
        peso_kg = st.number_input("Peso (kg)?", min_value=0.0, format="%.3f")
        altura_cm = st.number_input("Altura (cm)?", min_value=0.0, format="%.2f")
        largura_cm = st.number_input("Largura (cm)?", min_value=0.0, format="%.2f")
        profundidade_cm = st.number_input("Profundidade (cm)?", min_value=0.0, format="%.2f")
        st.subheader("Custos de Material")
        tipo_argila_escolha = st.radio("Qual argila foi usada?",
                                       ("Argila Própria", f"Argila do Ateliê (R$ {PRECO_ARGILA_ATELIE_KG}/kg)"), index=0)
        preco_argila_propria_input = 0.0
        if tipo_argila_escolha == "Argila Própria":
            tipo_argila_final = 'propria'
            preco_argila_propria_input = st.number_input("Preço do kg da sua argila? (R$)", min_value=0.0, format="%.2f")
        else:
            tipo_argila_final = 'atelie'
        
        submit_button = st.form_submit_button(label="Adicionar e Salvar Peça")

    if submit_button:
        if not nome_pessoa or not tipo_peca or not data_producao or peso_kg == 0:
            st.error("Por favor, preencha pelo menos o Nome, Tipo, Data e Peso (peso não pode ser zero).")
        else:
            with st.spinner("A criar e salvar a nova peça..."):
                nova_peca = Peca(
                    data_producao=data_producao, nome_pessoa=nome_pessoa, tipo_peca=tipo_peca,
                    peso_kg=peso_kg, altura_cm=altura_cm, largura_cm=largura_cm,
                    profundidade_cm=profundidade_cm, 
                    tipo_argila=tipo_argila_final, preco_argila_propria=preco_argila_propria_input
                )
                if salvar_nova_peca(nova_peca, uploaded_file):
                    st.success(f"✅ Peça '{nova_peca.tipo_peca}' adicionada e salva no Supabase!")
                    st.balloons(); st.session_state.inventario.insert(0, nova_peca) 
                else: st.error("Erro ao salvar os dados no Supabase.")

# --- PÁGINA 4: EXCLUIR PEÇA ---
elif pagina == "Excluir Peça":
    st.header("Excluir Peça")
    st.warning("Atenção: Esta ação é permanente e não pode ser desfeita.")
    
    inventario = st.session_state.inventario
    
    if not inventario:
        st.info("Não há peças no inventário para excluir.")
    else:
        opcoes_pecas = {f"{p.data_producao} - {p.tipo_peca} (por {p.nome_pessoa})": p for p in inventario}
        peca_selecionada_nome = st.selectbox("Selecione a peça que deseja excluir:", ["Selecione..."] + list(opcoes_pecas.keys()))
        
        if peca_selecionada_nome != "Selecione...":
            peca_obj = opcoes_pecas[peca_selecionada_nome]
            st.subheader("Você selecionou esta peça:")
            image_url = get_public_url(peca_obj.image_path)
            if image_url: st.image(image_url, width=200)
            st.write(f"**Tipo:** {peca_obj.tipo_peca}"); st.write(f"**Pessoa:** {peca_obj.nome_pessoa}")
            st.write(f"**Custo Total:** R$ {peca_obj.total:.2f}"); st.divider()
            
            if st.button(f"Confirmar Exclusão Permanente de '{peca_obj.tipo_peca}'", type="primary"):
                with st.spinner("Excluindo peça..."):
                    if excluir_peca_db(peca_obj):
                        st.success("Peça excluída com sucesso!")
                        st.session_state.inventario = [p for p in st.session_state.inventario if p.id != peca_obj.id]
                        st.rerun()
                    else: st.error("Falha ao excluir a peça.")