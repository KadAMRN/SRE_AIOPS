# streamlit_app.py
import streamlit as st
import pandas as pd
import time
import sys
import asyncio
from typing import List, Dict, Any
from dotenv import load_dotenv

# Ajouter la racine du projet au path pour permettre les imports
sys.path.append('.')

from ingestion.ingestion import ingest_data, stream_data_simulator
from recommendation.agent import create_sre_agent
from google.adk import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService
from google.genai import types

load_dotenv()

# --- Configuration de la Page Streamlit ---
st.set_page_config(
    page_title="Dashboard SRE IA",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Fonctions de l'Application ---

def initialize_session_state():
    """Initialise toutes les variables nécessaires dans l'état de la session Streamlit."""
    if 'is_running' not in st.session_state:
        st.session_state.is_running = False
    if 'data_df' not in st.session_state:
        st.session_state.data_df = ingest_data('rapport.json')
    if 'sre_agent' not in st.session_state:
        # On ne crée l'agent qu'une seule fois pour éviter de multiples connexions
        st.session_state.sre_agent = create_sre_agent()
    if 'runner' not in st.session_state:
        # Initialize Google ADK Runner
        app_name = 'sre_dashboard'
        session_service = InMemorySessionService()
        artifact_service = InMemoryArtifactService()
        st.session_state.runner = Runner(
            app_name=app_name,
            agent=st.session_state.sre_agent,
            artifact_service=artifact_service,
            session_service=session_service,
        )
        st.session_state.app_name = app_name
        st.session_state.session_service = session_service
        st.session_state.user_id = 'sre_user'
        st.session_state.session_id = None
    if 'live_log' not in st.session_state:
        st.session_state.live_log = []
    if 'agent_reports' not in st.session_state:
        st.session_state.agent_reports = []
    if 'metrics_history' not in st.session_state:
        # DataFrame pour stocker les données des graphiques
        st.session_state.metrics_history = pd.DataFrame(columns=['timestamp', 'cpu_usage', 'latency_ms', 'error_rate'])
    if 'data_stream' not in st.session_state:
        st.session_state.data_stream = None
    if 'batch_records' not in st.session_state:
        st.session_state.batch_records = []
    if 'batch_counter' not in st.session_state:
        st.session_state.batch_counter = 0
    if 'is_paused' not in st.session_state:
        st.session_state.is_paused = False
    if 'waiting_for_continue' not in st.session_state:
        st.session_state.waiting_for_continue = False


async def initialize_agent_session():
    """Initialize the agent session asynchronously."""
    if st.session_state.session_id is None:
        session = await st.session_state.session_service.create_session(
            app_name=st.session_state.app_name, 
            user_id=st.session_state.user_id
        )
        st.session_state.session_id = session.id


async def invoke_agent_async(prompt: str) -> str:
    """Invoke the agent asynchronously and return the response."""
    if st.session_state.session_id is None:
        await initialize_agent_session()
    
    content = types.Content(
        role='user', parts=[types.Part.from_text(text=prompt)]
    )
    
    response_parts = []
    async for event in st.session_state.runner.run_async(
        user_id=st.session_state.user_id,
        session_id=st.session_state.session_id,
        new_message=content,
    ):
        if event.content.parts and event.content.parts[0].text:
            response_parts.append(event.content.parts[0].text)
    
    return '\n'.join(response_parts)


def invoke_agent(prompt: str) -> str:
    """Synchronous wrapper for the async agent invocation."""
    try:
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in a running event loop, we need to use a different approach
                import threading
                import concurrent.futures
                
                def run_async():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(invoke_agent_async(prompt))
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    return future.result()
            else:
                return loop.run_until_complete(invoke_agent_async(prompt))
        except RuntimeError:
            # No event loop exists, create a new one
            return asyncio.run(invoke_agent_async(prompt))
    except Exception as e:
        raise Exception(f"Error invoking agent: {str(e)}")


def toggle_analysis():
    """Inverse l'état de la simulation (Démarrer/Arrêter)."""
    st.session_state.is_running = not st.session_state.is_running
    if not st.session_state.is_running:
        # Réinitialiser si on arrête
        st.session_state.data_stream = None
        st.session_state.batch_records = []
        st.session_state.is_paused = False
        st.session_state.waiting_for_continue = False


def continue_analysis():
    """Fonction pour continuer l'analyse après une pause."""
    st.session_state.waiting_for_continue = False
    st.session_state.is_paused = False


# --- Interface Utilisateur ---

st.title("🤖 Dashboard de Supervision SRE avec Agent IA")
st.markdown("Cette application simule un flux de données d'infrastructure, détecte les anomalies et génère des recommandations via un agent IA.")

# --- Panneau de Contrôle (Sidebar) ---
with st.sidebar:
    st.header("⚙️ Panneau de Contrôle")
    
    # L'hyperparamètre pour la taille des lots
    batch_size = st.slider(
        "Taille des lots pour l'Agent", 
        min_value=2, 
        max_value=20, 
        value=3, 
        step=1,
        help="Nombre d'enregistrements à envoyer à l'agent en une seule fois."
    )
    
    # L'hyperparamètre pour la vitesse
    simulation_delay = st.slider(
        "Vitesse de la simulation (secondes)", 
        min_value=0.0, 
        max_value=5.0, 
        value=1.0, 
        step=0.5,
        help="Délai entre chaque point de donnée pour ralentir ou accélérer la simulation."
    )
    
    # Bouton pour démarrer ou arrêter l'analyse
    st.button(
        "Arrêter l'Analyse" if st.session_state.get('is_running', False) else "Démarrer l'Analyse",
        on_click=toggle_analysis,
        type="primary" if not st.session_state.get('is_running', False) else "secondary"
    )
    st.warning("N'oubliez pas de lancer le `mcp_server.py` dans un terminal séparé avant de démarrer l'analyse.")


# --- Initialisation de l'état ---
initialize_session_state()

# --- Affichage du Dashboard ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("CPU Usage (%)")
    cpu_chart_placeholder = st.empty()

with col2:
    st.subheader("Latence (ms)")
    latency_chart_placeholder = st.empty()

st.subheader("📝 Rapports de l'Agent SRE")
agent_reports_placeholder = st.container()

# Bouton pour continuer l'analyse (affiché seulement si en attente)
if st.session_state.get('waiting_for_continue', False):
    st.info("🔄 L'analyse est en pause après la génération d'un rapport. Cliquez sur 'Continuer' pour reprendre.")
    if st.button("Continuer l'Analyse", type="primary", on_click=continue_analysis):
        st.rerun()

st.subheader("📟 Log en direct")
live_log_placeholder = st.empty()


# --- Logique Principale de l'Application ---
if st.session_state.is_running and not st.session_state.get('waiting_for_continue', False):
    if st.session_state.data_stream is None:
        # Démarrer un nouveau flux si ce n'est pas déjà fait
        st.session_state.data_stream = stream_data_simulator(st.session_state.data_df, delay=0) # Le délai est géré par st.sleep

    try:
        # Boucle sur le générateur de données
        record = next(st.session_state.data_stream)
        
        # Mise à jour des données pour les graphiques
        new_data = pd.DataFrame([{
            "timestamp": pd.to_datetime(record['timestamp']),
            "cpu_usage": record['cpu_usage'],
            "latency_ms": record['latency_ms'],
            "error_rate": record['error_rate']
        }])
        st.session_state.metrics_history = pd.concat([st.session_state.metrics_history, new_data], ignore_index=True).tail(100) # Garder les 100 derniers points
        
        # Mise à jour des graphiques
        cpu_chart_placeholder.line_chart(st.session_state.metrics_history.set_index('timestamp')['cpu_usage'])
        latency_chart_placeholder.line_chart(st.session_state.metrics_history.set_index('timestamp')['latency_ms'])

        # Ajout de l'enregistrement au lot en cours
        st.session_state.batch_records.append(record)
        
        # Log en direct
        st.session_state.live_log.insert(0, f"✔️ ({pd.to_datetime(record['timestamp']).strftime('%H:%M:%S')}) Donnée reçue.")
        live_log_placeholder.text_area("", value="\n".join(st.session_state.live_log), height=200)

        # Si le lot est plein, on l'envoie à l'agent
        if len(st.session_state.batch_records) >= batch_size:
            st.session_state.batch_counter += 1
            batch_num = st.session_state.batch_counter
            
            st.session_state.live_log.insert(0, f"--- 📦 Envoi du Lot #{batch_num} à l'agent... ---")
            live_log_placeholder.text_area("", value="\n".join(st.session_state.live_log), height=200)

            prompt = f"Analyse ce lot de données de monitoring, fournis une synthèse et des recommandations. Lot de données: {st.session_state.batch_records}"
            
            try:
                with st.spinner(f"L'agent SRE analyse le lot #{batch_num}..."):
                    agent_response = invoke_agent(prompt)
                
                st.session_state.agent_reports.insert(0, (batch_num, agent_response))
                st.session_state.live_log.insert(0, f"--- ✅ Rapport de l'Agent reçu pour le Lot #{batch_num} ---")
                
                # Mettre l'analyse en pause après chaque rapport
                st.session_state.waiting_for_continue = True
                st.session_state.is_paused = True
                
            except Exception as e:
                st.error(f"Erreur lors de l'invocation de l'agent pour le lot #{batch_num}: {e}")
                st.session_state.live_log.insert(0, f"--- ❌ Erreur Agent pour le Lot #{batch_num} ---")

            # Réinitialiser le lot
            st.session_state.batch_records = []
            
            # Forcer la mise à jour de l'affichage pour montrer le bouton "Continuer"
            st.rerun()

        # Affichage des rapports de l'agent
        with agent_reports_placeholder:
            for i, (batch_num, report) in enumerate(st.session_state.agent_reports):
                with st.expander(f"Rapport d'Analyse - Lot #{batch_num}", expanded=(i==0)):
                    st.markdown(report)
        
        # Continuer seulement si pas en pause
        if not st.session_state.get('waiting_for_continue', False):
            time.sleep(simulation_delay)
            st.rerun() # Force Streamlit à ré-exécuter pour la prochaine itération

    except StopIteration:
        st.success("La simulation est terminée. Tous les points de données ont été traités.")
        st.session_state.is_running = False
        st.rerun()
    except Exception as e:
        st.error(f"Une erreur critique est survenue: {e}")
        st.session_state.is_running = False

elif not st.session_state.get('is_running', False) and len(st.session_state.get('agent_reports', [])) > 0:
    # Cas où l'analyse est arrêtée mais il y a des rapports à afficher
    st.info("L'analyse est arrêtée. Voici les derniers rapports générés.")
    
    # Affichage des graphiques même quand l'analyse est arrêtée
    if not st.session_state.metrics_history.empty:
        cpu_chart_placeholder.line_chart(st.session_state.metrics_history.set_index('timestamp')['cpu_usage'])
        latency_chart_placeholder.line_chart(st.session_state.metrics_history.set_index('timestamp')['latency_ms'])
    
    # Affichage des rapports de l'agent même quand l'analyse est arrêtée
    with agent_reports_placeholder:
        for i, (batch_num, report) in enumerate(st.session_state.agent_reports):
            with st.expander(f"Rapport d'Analyse - Lot #{batch_num}", expanded=(i==0)):
                st.markdown(report)

elif st.session_state.get('waiting_for_continue', False):
    # Affichage des graphiques même pendant la pause
    if not st.session_state.metrics_history.empty:
        cpu_chart_placeholder.line_chart(st.session_state.metrics_history.set_index('timestamp')['cpu_usage'])
        latency_chart_placeholder.line_chart(st.session_state.metrics_history.set_index('timestamp')['latency_ms'])
    
    # Affichage des rapports quand on attend la continuation
    with agent_reports_placeholder:
        for i, (batch_num, report) in enumerate(st.session_state.agent_reports):
            with st.expander(f"Rapport d'Analyse - Lot #{batch_num}", expanded=(i==0)):
                st.markdown(report)