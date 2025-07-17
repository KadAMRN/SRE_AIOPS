# recommendation/mcp_server.py
import sys
import pandas as pd
from typing import List, Dict, Any

# Ajouter la racine du projet au path pour permettre les imports
# depuis les dossiers frères 'analyse' et 'ingestion'.
sys.path.append('.')

from mcp.server.fastmcp import FastMCP
from analyse.analyse import AnomalyDetector
from ingestion.ingestion import ingest_data # Nécessaire pour pré-entraîner le détecteur

# --- Configuration du Serveur ---
HOST = "localhost"
PORT = 3000

# --- Initialisation de l'Outil d'Analyse ---
print("🔧 Initialisation du serveur MCP d'analyse...")

# 1. Charger les données initiales pour "entraîner" le détecteur d'anomalies.
#    Cela lui permet de connaître les moyennes et écarts-types normaux du système.
initial_data_df = ingest_data('rapport.json')
if initial_data_df is None:
    print("❌ ERREUR: Impossible de charger 'rapport.json'. Le serveur ne peut pas démarrer.")
    sys.exit(1)

# 2. Définir la configuration pour la détection d'anomalies.
ANALYSIS_CONFIG = {
    'rolling_window_size': 20,
    'metrics_to_check': {
        'cpu_usage': {'threshold': 90, 'global_std_factor': 3, 'rolling_std_factor': 2, 'delta_threshold': 20},
        'memory_usage': {'threshold': 85, 'global_std_factor': 3, 'rolling_std_factor': 2, 'delta_threshold': 20},
        'disk_usage': {'threshold': 90, 'global_std_factor': 3, 'rolling_std_factor': 2},
        'latency_ms': {'threshold': 300, 'global_std_factor': 3, 'rolling_std_factor': 2.5, 'delta_threshold': 100},
        'error_rate': {'threshold': 0.1, 'delta_threshold': 0.05},
        'temperature_celsius': {'threshold': 80}
    }
}

# 3. Créer et entraîner l'instance du détecteur.
anomaly_detector = AnomalyDetector(config=ANALYSIS_CONFIG)
anomaly_detector.compute_global_stats(initial_df=initial_data_df)

print(f"✅ Détecteur d'anomalies prêt.")

# 4. Créer le serveur MCP.
mcp = FastMCP("Serveur d'Analyse de Métriques", host=HOST, port=PORT)

# --- Définition de l'Outil MCP ---
@mcp.tool(description="Analyse un lot (batch) de points de données pour détecter des anomalies.")
def analyze_metrics_batch(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Prend une liste d'enregistrements, les analyse un par un avec le détecteur,
    et retourne un rapport consolidé des anomalies pour le lot.
    """
    print(f"MCP: Reçu une demande d'analyse pour un lot de {len(records)} enregistrements.")
    all_anomalies = []
    
    # Nouveau: Collecter les données des métriques pour le rapport
    metrics_summary = {}
    
    for record in records:
        # L'agent peut envoyer le timestamp comme une chaîne, on s'assure qu'il est au bon format.
        if isinstance(record.get('timestamp'), str):
             record['timestamp'] = pd.to_datetime(record['timestamp'])
        
        # Extraire les métriques pour le résumé
        for metric in ANALYSIS_CONFIG['metrics_to_check']:
            if metric in record:
                if metric not in metrics_summary:
                    metrics_summary[metric] = {
                        'values': [],
                        'threshold': ANALYSIS_CONFIG['metrics_to_check'][metric].get('threshold', 'N/A'),
                        'global_mean': anomaly_detector.global_stats.get('mean', {}).get(metric, 'N/A'),
                        'global_std': anomaly_detector.global_stats.get('std', {}).get(metric, 'N/A')
                    }
                metrics_summary[metric]['values'].append(record[metric])
        
        detected = anomaly_detector.detect(record)
        if detected:
            all_anomalies.append({
                "timestamp": str(record['timestamp']),
                "anomalies_detectees": detected
            })
    
    # Calculer les valeurs actuelles (moyenne du batch)
    for metric in metrics_summary:
        values = metrics_summary[metric]['values']
        metrics_summary[metric]['current_value'] = sum(values) / len(values)
        metrics_summary[metric]['min_value'] = min(values)
        metrics_summary[metric]['max_value'] = max(values)
        metrics_summary[metric]['count'] = len(values)
    
    # Créer un rapport détaillé pour l'agent
    detailed_report = {
        "status": "ANOMALIES_DETECTED" if all_anomalies else "OK",
        "rapport_anomalies": all_anomalies,
        "metrics_summary": metrics_summary,
        "batch_info": {
            "total_records": len(records),
            "anomalous_records": len(all_anomalies),
            "time_range": {
                "start": str(min(record['timestamp'] for record in records)),
                "end": str(max(record['timestamp'] for record in records))
            }
        },
        "configuration": {
            "seuils_critiques": {
                metric: config.get('threshold', 'N/A') 
                for metric, config in ANALYSIS_CONFIG['metrics_to_check'].items()
            }
        }
    }
    
    if not all_anomalies:
        print("MCP: Aucune anomalie détectée dans ce lot.")
    else:
        print(f"MCP: {len(all_anomalies)} points de données avec anomalies trouvés.")
    
    return detailed_report

# --- Exécution du Serveur ---
if __name__ == "__main__":
    print(f"🚀 Démarrage du serveur MCP sur http://{HOST}:{PORT}")
    print("Utilisez CTRL+C pour arrêter le serveur.")
    try:
        mcp.run(transport="sse")
    except KeyboardInterrupt:
        print("\nSIGINT reçu, arrêt du serveur MCP.")
    except Exception as e:
        print(f"Erreur inattendue: {e}")
    finally:
        print("Serveur MCP arrêté.")
