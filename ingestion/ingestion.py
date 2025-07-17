import pandas as pd
import time
import sys
from typing import Iterator, Dict, Any, Optional

# Pour que Python puisse trouver le module dans le dossier voisin 'analyse'
sys.path.append('.')

from analyse.analyse import AnomalyDetector

# La fonction ingest_data reste la même qu'avant...
def ingest_data(file_path: str) -> Optional[pd.DataFrame]:
    """
    Ingère les données depuis un fichier JSON, les nettoie et les prépare pour l'analyse.
    """
    try:
        df = pd.read_json(file_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if 'service_status' in df.columns:
            service_status_df = pd.json_normalize(df['service_status'])
            df = df.join(service_status_df.add_prefix('service_status_'))
            df = df.drop('service_status', axis=1)
        df = df.sort_values(by='timestamp').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"❌ ERREUR lors de l'ingestion des données : {e}")
        return None

# La fonction de simulation reste la même...
def stream_data_simulator(df: pd.DataFrame, delay: float = 0.1) -> Iterator[Dict[str, Any]]:
    print("\n--- 🎬 Lancement de la simulation du flux de données ---")
    try:
        for _, row in df.iterrows():
            yield row.to_dict()
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\n--- 🛑 Simulation arrêtée. ---")
    finally:
        print("--- ✅ Fin du flux. ---")
        
# --- Point d'entrée principal (modifié) ---
if __name__ == '__main__':
    # --- CONFIGURATION DE L'ANALYSE ---
    # C'est ici que l'on définit toutes nos règles. C'est facilement modifiable.
    ANALYSIS_CONFIG = {
        'rolling_window_size': 20, # Fenêtre pour la moyenne glissante
        'metrics_to_check': {
            'cpu_usage': {
                'threshold': 90, # Seuil critique
                'global_std_factor': 3, # N x écart-type global
                'rolling_std_factor': 2, # N x écart-type glissant
                'delta_threshold': 20, # Hausse de 20% en 1 step
            },
            'memory_usage': {
                'threshold': 85,
                'global_std_factor': 3,
                'rolling_std_factor': 2,
                'delta_threshold': 20,
            },
            'disk_usage': {
                'threshold': 90,
                'global_std_factor': 3,
                'rolling_std_factor': 2,
            },
            'latency_ms': {
                'threshold': 300,
                'global_std_factor': 3,
                'rolling_std_factor': 2.5,
                'delta_threshold': 100,
            },
            'error_rate': {
                'threshold': 0.1, # 10% d'erreurs
                 'delta_threshold': 0.05,
            },
            'temperature_celsius': {
                'threshold': 80,
            }
        }
    }

    # Étape 1: Ingestion
    data_df = ingest_data(file_path='rapport.json')
    
    if data_df is not None:
        # Étape 2: Initialisation et entraînement du noeud d'analyse
        anomaly_detector = AnomalyDetector(config=ANALYSIS_CONFIG)
        anomaly_detector.fit(initial_df=data_df)
        
        # Étape 3: Lancement de la simulation et analyse en temps réel
        data_stream = stream_data_simulator(data_df, delay=0.1)
        
        print("\n--- 📡 Démarrage de l'analyse du flux en temps réel ---")
        for record_data in data_stream:
            
            # NOEUD D'ANALYSE : on passe la donnée reçue au détecteur
            anomalies = anomaly_detector.detect(record_data)
            
            timestamp = pd.to_datetime(record_data['timestamp']).strftime('%H:%M:%S')
            
            if anomalies:
                # Si des anomalies sont détectées, on les affiche
                print(f"🚨 ({timestamp}) Anomalies détectées !")
                for anom in anomalies:
                    print(f"   - {anom}")
                # C'est ici qu'on appellera le noeud de recommandation
            else:
                print(f"✔️ ({timestamp}) RAS. Tous les indicateurs sont normaux.")

