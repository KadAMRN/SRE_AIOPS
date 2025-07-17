# main.py (à la racine du projet)
import sys
import time
from typing import List, Dict, Any

# Assurer que les modules dans les sous-dossiers sont importables
sys.path.append('.')

from ingestion.ingestion import ingest_data, stream_data_simulator
from recommendation.agent import create_sre_agent

# --- Configuration de l'Orchestrateur ---
# L'hyperparamètre pour la taille des lots que l'agent analyse à chaque fois.
BATCH_SIZE = 15
SIMULATION_DELAY = 0.05 # Délai entre chaque "tick" de la simulation en secondes

def run_analysis_pipeline():
    """
    Orchestre le pipeline complet: ingestion -> simulation -> analyse par l'agent -> recommandation.
    """
    print("--- 🚀 Démarrage du Pipeline d'Analyse d'Infrastructure ---")
    
    # Étape 1: Ingestion des données historiques
    print("\n[Étape 1/3] Ingestion des données initiales...")
    data_df = ingest_data('rapport.json')
    if data_df is None:
        print("Pipeline arrêté car les données n'ont pas pu être chargées.")
        return
        
    # Étape 2: Création de l'agent SRE
    print("\n[Étape 2/3] Initialisation de l'agent d'analyse...")
    print("❗ IMPORTANT: Assurez-vous que le serveur MCP (`recommendation/mcp_server.py`) est lancé dans un autre terminal.")
    try:
        sre_agent = create_sre_agent()
    except Exception as e:
        print(f"❌ ERREUR: Impossible de créer l'agent. Le serveur MCP est-il bien lancé ? ({e})")
        return

    # Étape 3: Simulation et traitement par lots
    print(f"\n[Étape 3/3] Lancement de la simulation et de l'analyse par lots de {BATCH_SIZE} enregistrements...")
    data_stream = stream_data_simulator(data_df, delay=SIMULATION_DELAY)
    
    batch_records: List[Dict[str, Any]] = []
    batch_counter = 0

    for record in data_stream:
        # On convertit le timestamp en string pour la sérialisation JSON vers l'agent
        record['timestamp'] = record['timestamp'].isoformat()
        batch_records.append(record)
        
        # Quand le lot est plein, on le soumet à l'agent
        if len(batch_records) >= BATCH_SIZE:
            batch_counter += 1
            print(f"\n--- 📦 Envoi du Lot #{batch_counter} à l'agent pour analyse... ---")
            
            # On construit le prompt pour l'agent.
            # L'agent va d'abord appeler son outil `analyze_metrics_batch` avec `batch_records`.
            # Puis, il utilisera le rapport d'anomalies retourné par l'outil pour formuler sa réponse finale.
            prompt = f"""
            Voici un lot de données de monitoring. Utilise ton outil pour les analyser, puis fournis une synthèse et des recommandations basées sur les anomalies trouvées.
            Données du lot: {batch_records}
            """
            
            try:
                agent_response = sre_agent.invoke(prompt)
                print("\n--- 🧠 Réponse de l'Agent SRE ---")
                print(agent_response)
                print("---------------------------------\n")
            except Exception as e:
                print(f"❌ ERREUR lors de l'invocation de l'agent: {e}")

            batch_records = [] # Réinitialisation du lot

    print("--- ✅ Pipeline d'analyse terminé. ---")

if __name__ == "__main__":
    run_analysis_pipeline()
