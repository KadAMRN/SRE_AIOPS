import pandas as pd
from typing import List, Dict, Any, Optional

class AnomalyDetector:
    """
    Une classe pour détecter les anomalies dans un flux de métriques techniques.
    Elle utilise une combinaison de méthodes :
    1. Seuils statiques (ex: CPU > 90%).
    2. Écart-type par rapport à la moyenne globale.
    3. Écart-type par rapport à une moyenne glissante (pour détecter les déviations récentes).
    4. Différence (delta) par rapport à la valeur précédente (pour détecter les hausses brusques).
    5. Statut direct des services (offline/degraded).
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialise le détecteur avec une configuration.

        Args:
            config (Dict[str, Any]): Un dictionnaire contenant les seuils et paramètres.
        """
        self.config = config
        self.global_stats = {}  # Pour stocker les moyennes et écarts-types globaux
        self.history = pd.DataFrame() # Pour stocker l'historique des données reçues

    def compute_global_stats(self, initial_df: pd.DataFrame):
        """
        Calcule les statistiques globales à partir d'un jeu de données initial.
        C'est l'étape "d'entraînement" de notre détecteur.
        """
        print("🔍 Entraînement du détecteur d'anomalies sur les données initiales...")
        # On ne calcule les stats que sur les colonnes numériques
        numeric_cols = initial_df.select_dtypes(include='number').columns
        self.global_stats['mean'] = initial_df[numeric_cols].mean()
        self.global_stats['std'] = initial_df[numeric_cols].std()
        print("✅ Détecteur prêt.")

    def detect(self, record: Dict[str, Any]) -> List[str]:
        """
        Analyse un enregistrement unique et retourne une liste des anomalies détectées.
        """
        anomalies = []
        
        # Conversion du record en Series Pandas pour faciliter les calculs
        record_s = pd.Series(record)
        
        # Mise à jour de l'historique avec la nouvelle donnée
        self.history = pd.concat([self.history, pd.DataFrame([record])], ignore_index=True)
        # On garde une fenêtre d'historique limitée pour ne pas saturer la mémoire
        window = self.config.get('rolling_window_size', 20)
        self.history = self.history.tail(window)

        # 1. Détection sur les statuts de service
        for col in [c for c in record_s.index if 'service_status_' in c]:
            if record_s[col] in ['offline', 'degraded']:
                anomalies.append(f"ALERTE: Le service '{col.replace('service_status_', '')}' est {record_s[col].upper()}.")

        # 2. Détection sur les métriques numériques
        for metric in self.config['metrics_to_check']:
            if metric not in record_s or pd.isna(record_s[metric]):
                continue

            value = record_s[metric]
            conf = self.config['metrics_to_check'][metric]
            
            # Seuil statique
            if 'threshold' in conf and value > conf['threshold']:
                anomalies.append(f"CRITIQUE: '{metric}' ({value}) dépasse le seuil de {conf['threshold']}.")
            
            # Écart-type global
            mean_g = self.global_stats['mean'].get(metric, 0)
            std_g = self.global_stats['std'].get(metric, 1) # Eviter division par zéro
            if std_g > 0 and abs(value - mean_g) > conf.get('global_std_factor', 3) * std_g:
                 anomalies.append(f"AVERTISSEMENT: '{metric}' ({value}) est anormalement éloigné de la moyenne globale ({mean_g:.2f}).")
            
            # Analyses basées sur l'historique (si on a assez de données)
            if len(self.history) > 1:
                # Moyenne glissante
                mean_r = self.history[metric].rolling(window=window, min_periods=2).mean().iloc[-1]
                std_r = self.history[metric].rolling(window=window, min_periods=2).std().iloc[-1]
                if pd.notna(std_r) and std_r > 0 and abs(value - mean_r) > conf.get('rolling_std_factor', 2) * std_r:
                    anomalies.append(f"AVERTISSEMENT: '{metric}' ({value}) dévie de sa moyenne glissante ({mean_r:.2f}).")
                
                # Delta (hausse rapide)
                prev_value = self.history[metric].iloc[-2]
                delta = value - prev_value
                if 'delta_threshold' in conf and delta > conf['delta_threshold']:
                    anomalies.append(f"INFO: Hausse rapide de '{metric}' de {delta:.2f}.")

        print(f"🔍 Anomalies détectées: {anomalies}")
        return anomalies

