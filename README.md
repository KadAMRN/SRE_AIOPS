# Rapport Technique : Conception et Implémentation d'une Plateforme AIOps Hybride


Ce document détaille la conception et la réalisation d'une plateforme AIOps visant à transformer la supervision d'infrastructure d'un processus réactif à une gestion proactive et intelligente. La solution développée répond à la problématique d'un CTO submergé par des données de monitoring complexes en automatisant la détection d'anomalies et en fournissant des plans d'action clairs et priorisés.

La philosophie est de combiner le meilleur de deux mondes : la **rigueur de l'analyse de données classique** pour une détection factuelle et objective, et la **puissance de raisonnement de l'IA Générative** pour l'interprétation, la corrélation et la recommandation stratégique. Le résultat est un système qui non seulement alerte, mais qui **assiste activement la prise de décision**.

## 2. Philosophie d'Ingénierie : Une Architecture Hybride à Deux Niveaux

Le défi principal d'un système AIOps est de trouver le juste équilibre entre la fiabilité des données et l'intelligence de l'interprétation. Une approche 100% déterministe manquerait de contexte et générerait un bruit d'alertes important, tandis qu'une approche 100% IA Générative serait non fiable, coûteuse et sujette aux hallucinations pour l'analyse de données brutes.

Nous avons donc conçu une **architecture hybride à deux niveaux**, qui sépare fondamentalement les tâches qui exigent une objectivité mathématique de celles qui bénéficient d'une capacité de raisonnement avancée.

### Niveau 1 : Le Socle Analytique Déterministe

**Objectif :** Atteindre une objectivité et une fiabilité absolues dans le traitement des données brutes et la détection de signaux. Cette couche a pour mission de transformer le bruit en information factuelle.

**Pourquoi du code et des algorithmes classiques ?**
Pour les premières étapes du pipeline, nous avons fait le choix délibéré d'utiliser des approches algorithmiques et statistiques. Un système de monitoring ne peut tolérer l'incertitude ou la non-répétabilité. Pour un même jeu de données en entrée, la détection d'une anomalie doit être **identique et prévisible à chaque exécution**. L'utilisation de code Python et de bibliothèques comme Pandas garantit ce comportement **non-stochastique**. Ce socle répond à la question : **"Quoi s'est-il passé d'anormal ?"** de manière factuelle, en produisant une vérité de terrain ("ground truth") sur laquelle l'IA pourra s'appuyer. De plus, cette approche est extrêmement performante et peu coûteuse en ressources, ce qui est essentiel pour le traitement de volumes de données importants.

### Niveau 2 : La Couche de Raisonnement par IA Générative

**Objectif :** Transformer les faits bruts en informations actionnables et en intelligence stratégique.

**Pourquoi l'IA Générative ?**
Une liste d'anomalies, même précise, n'est souvent qu'une liste de symptômes. La véritable intelligence métier réside dans la capacité à **corréler** ces symptômes pour diagnostiquer la maladie sous-jacente (ex: "Le pic de latence sur le service web à 14h02 est directement corrélé à la saturation du CPU et à la dégradation de l'API Gateway, qui coïncide elle-même avec une augmentation des I/O sur la base de données. La cause racine est probablement une requête SQL inefficace."). Ces tâches de raisonnement complexe, d'analyse causale et de génération de langage naturel sont précisément là où les LLM excellent. En utilisant un agent IA (Google ADK), nous déléguons la question du **"Pourquoi cela se produit-il et que devons-nous faire ?"** à un système spécialisé dans ce type de raisonnement. Cette architecture hybride nous permet donc d'exploiter la rigueur des algorithmes pour l'analyse factuelle et la flexibilité des LLM pour la prise de décision stratégique.

## 3. Décomposition Fonctionnelle du Pipeline

Chaque module de l'architecture a un rôle, des entrées et des sorties clairement définis.

### Module 1 : `analyse` - Le Moteur de Détection Scientifique

* **Rôle :** Fournir le cœur de la logique de détection d'anomalies. C'est notre moteur d'analyse factuelle.
* **Input :** Un enregistrement de données unique (format dictionnaire Python).
* **Traitement :**
  1. **Calcul des Statistiques (au démarrage) :** Le module calcule en amont la moyenne ($\\mu$) et l'écart-type ($\\sigma$) sur l'intégralité du jeu de données historique. Ceci établit une **ligne de base statistique** représentant le comportement "normal" du système sur le long terme.
  2. **Détection Hybride (pour chaque donnée) :** Une chaîne de validation est appliquée :
     * **Seuils Statiques :** Comparaison à des limites fixes (ex: `cpu_usage` > 90%). C'est notre filet de sécurité pour les violations de règles métier claires ou de contraintes physiques.
     * **Z-score Global :** Calcul du Z-score par rapport aux statistiques globales ($Z = |x - \\mu| / \\sigma$). Cela identifie les événements qui sont statistiquement rares et anormaux par rapport à l'historique complet. Par exemple, un service qui tourne habituellement à 20% de CPU et qui passe soudainement à 50% ne déclenchera pas un seuil statique, mais sera détecté comme un événement statistiquement improbable.
     * **Z-score sur Moyenne Glissante :** Pour éviter les fausses alertes dues aux variations de charge normales (ex: pic de trafic à midi), nous calculons le Z-score par rapport à une moyenne et un écart-type mobiles (sur les N derniers points). Cela rend la détection **adaptative au contexte récent**. Par exemple, un CPU à 70% peut être normal pendant un batch de nuit, mais très anormal en milieu d'après-midi. La moyenne glissante capture cette "normalité locale".
     * **Analyse de Vélocité (Delta) :** Calcul de la différence avec le point précédent ($x\\_t - x\\_{t-1}$). Cela permet de détecter des **changements brusques** qui sont souvent les premiers signes d'un incident, avant même que les seuils absolus ne soient atteints. Une augmentation soudaine du nombre de connexions actives, par exemple, peut signaler une attaque ou une boucle de "retry" bien avant que la latence ne se dégrade.
* **Output :** Une liste de chaînes de caractères décrivant les anomalies détectées de manière objective (ex: `["CRITIQUE: 'cpu_usage' (95) dépasse le seuil de 90."]` ).

### Module 2 : `recommendation` - L'Intelligence Artificielle en Action

Ce module est composé du serveur d'outils et de l'agent raisonneur.

#### 2a. Serveur MCP (L'Outil)

* **Rôle :** Exposer la logique du module `analyse` de manière sécurisée et scalable via une API réseau. Il agit comme une "boîte à outils" pour l'agent, garantissant que l'IA ne peut accéder qu'aux fonctions que nous autorisons.
* **Input :** Une requête réseau contenant un lot (batch) de données brutes.
* **Traitement :** Orchestre l'appel au module `analyse` pour chaque enregistrement du lot et agrège les résultats.
* **Output :** Une réponse réseau contenant un rapport structuré en JSON, qui est une collection de faits bruts et de statistiques sur le lot.

#### 2b. Agent SRE (Le Cerveau)

* **Rôle :** Simuler la démarche intellectuelle d'un ingénieur SRE expert.
* **Input :** Un prompt contenant un lot de données brutes et une instruction système très précise.
* **Traitement :**
  1. **Appel à l'Outil :** L'agent reçoit le lot de données et, pour obtenir des faits objectifs, il fait appel à son seul outil disponible : le serveur MCP.
  2. **Analyse du Rapport Factuel :** Il reçoit le rapport JSON de l'outil. Cette étape est cruciale, car elle **"ground"** le raisonnement de l'agent sur des données vérifiées, l'empêchant d'inventer des métriques ou de se baser sur des informations incorrectes.
  3. **Raisonnement et Génération :** En s'appuyant sur le rapport JSON et sur son instruction système, le LLM engage un processus de raisonnement pour corréler les anomalies, synthétiser les problèmes, identifier les causes probables et élaborer un plan d'action.
* **Output :** Un rapport final en Markdown, structuré, clair et directement présentable à un CTO.

### Module 3 : `streamlit_app` - L'Interface de Pilotage

* **Rôle :** Orchestrer le pipeline, offrir une interface de contrôle à l'utilisateur et visualiser les résultats de manière professionnelle. Il sert de pont entre l'utilisateur et le système complexe sous-jacent.
* **Input :** Les interactions de l'utilisateur (démarrage, réglage des hyperparamètres) et le flux de données du module `ingestion`.
* **Traitement :**
  1. Gère le cycle de vie de la simulation.
  2. Met à jour les graphiques en temps réel pour une visualisation immédiate.
  3. Regroupe les données en lots et les soumet à l'agent.
  4. Affiche les rapports de l'agent de manière lisible.
* **Output :** Une interface web interactive affichée dans le navigateur de l'utilisateur.

## 4. Justification des Choix Techniques

Cette section détaille les raisons qui ont motivé le choix des frameworks et technologies spécifiques pour chaque partie du projet.

* **Langage de Programmation : Python**
  * **Justification :** Le choix de Python s'est imposé naturellement. Il s'agit du langage de prédilection de l'écosystème de la Data Science et de l'Intelligence Artificielle. Sa syntaxe simple et sa vaste collection de bibliothèques (Pandas, etc.) en font un outil idéal pour le prototypage rapide et efficace, tout en étant suffisamment robuste pour des applications de production.

* **Framework Agentique : Google ADK (Agent Development Kit)**
  * **Justification :** Pour l'implémentation de l'agent, le framework Google ADK a été sélectionné. Ce choix a été motivé par une volonté d'explorer une technologie moderne et prometteuse, en complément de mon expérience sur d'autres frameworks comme Agno ou Semantic Kernel. L'objectif était d'évaluer sa prise en main et sa flexibilité. Le verdict est positif : ADK s'est révélé relativement simple et intuitif pour la mise en place d'un agent simple, bien que certaines tâches plus complexes puissent demander une verbosité de code plus importante.

* **Architecture de l'Outil : Serveur MCP (Model Context Protocol)**
  * **Justification :** Plutôt que de définir l'outil d'analyse comme une simple fonction Python locale, nous avons opté pour une architecture client-serveur via un MCP. Ce choix bien que plus complexe à mettre en place, offre un avantage majeur : le **découplage**. L'outil d'analyse, exposé via une API, devient agnostique au framework agentique. Si nous avions décidé que Google ADK n'était pas adapté, nous aurions pu basculer sur un autre framework en implémentant simplement un nouveau connecteur pour appeler notre serveur MCP, sans avoir à réécrire la logique de l'outil. Cela garantit la réutilisabilité et la pérennité de notre moteur d'analyse.

* **Interface de Démonstration : Streamlit**
  * **Justification :** Pour la visualisation et l'interaction, Streamlit a été choisi pour sa simplicité et sa rapidité de mise en œuvre. Il permet de créer des interfaces web interactives directement en Python, ce qui est parfait pour le prototypage et les démonstrations techniques. Il offre un excellent compromis entre effort de développement et qualité du rendu final.

* **Modèle de Langage (LLM) : Gemini Flash**
  * **Justification :** Le choix s'est porté sur Gemini Flash pour sa rapidité, un critère essentiel pour une application simulant un traitement en temps réel. L'objectif était d'obtenir des réponses rapides pour ne pas ralentir la démonstration. Pour ce cas d'usage, un raisonnement complexe n'était pas la priorité absolue, et la performance de Gemini Flash était donc tout à fait appropriée. Aucun ajustement des hyperparamètres (température, top-p) n'a été effectué, mais cela constitue une piste d'optimisation future pour affiner la créativité ou la rigueur des réponses de l'agent.

## 5. Guide de Lancement de l'Application

Suivez ces étapes pour installer et exécuter la solution.

### Prérequis

* Python 3.8 ou supérieur.
* `pip` et un environnement virtuel (`venv`) sont fortement recommandés pour isoler les dépendances.

### Installation

1. **Cloner le projet :**


2. **Créer et activer l'environnement virtuel :**
   ```
   python -m venv venv
   source venv/bin/activate  # Sur Windows: venv\\Scripts\\activate
   ```

3. **Installer les dépendances :** Créez un fichier `requirements.txt` à la racine du projet avec le contenu suivant, puis exécutez la commande d'installation.
   *Contenu de `requirements.txt`:*
   ```
   pandas
   streamlit
   python-dotenv
   google-generativeai
   google-adk
   uv
   ```
   *Commande d'installation:*
   ```
   pip install -r requirements.txt
   ```

4. **Configurer la clé API :** Créez un fichier nommé `.env` à la racine du projet et ajoutez votre clé API Google Gemini.
   *Contenu de `.env`:*
   ```
   GOOGLE_API_KEY="VOTRE_CLE_API_GEMINI_ICI"
   ```

### Exécution

L'application se lance en deux étapes, nécessitant deux terminaux distincts.

**Terminal 1 : Lancer le Serveur d'Analyse (MCP)**
Ce service doit être actif pour que l'agent puisse fonctionner.
```
# Assurez-vous d'être à la racine du projet
uv run recommendation/mcp_server.py
```

Laissez ce terminal ouvert. Il confirmera que le serveur est démarré et en attente de requêtes.

**Terminal 2 : Lancer l'Interface Streamlit**
C'est le point d'entrée principal pour la démonstration.
```
# Dans un nouveau terminal, à la racine du projet
streamlit run streamlit_app.py
```

Votre navigateur s'ouvrira automatiquement sur le tableau de bord. Vous pourrez alors utiliser le panneau de contrôle pour lancer et piloter la simulation.

## 6. Vision Produit et Axes d'Amélioration Futurs

Cette implémentation constitue une preuve de concept robuste. Pour la faire évoluer vers une plateforme AIOps de production, la roadmap suivante est envisagée :

### Axe 1 : Scalabilité et Intégration à l'Écosystème Existant

* **Connecteurs de Données Réels :** Remplacer le simulateur par des connecteurs modulaires pour des sources de données standards comme **Kafka**, **Prometheus**, ou des services de logs cloud (CloudWatch, Google Cloud Logging). L'utilisation de Kafka, par exemple, permettrait de découpler la production de métriques de leur consommation, offrant une meilleure résilience et la possibilité à plusieurs services (alerting, archivage, analyse) de consommer le même flux.
* **Persistance des Données :** Intégrer une base de données optimisée pour les séries temporelles (ex: **TimescaleDB**, **InfluxDB**) pour stocker l'historique des métriques et des rapports de l'agent, permettant des analyses de tendance sur le long terme et la détection de problèmes de fond.
* **Déploiement Conteneurisé :** Packager chaque service (Serveur MCP, Streamlit App) avec **Docker** et les orchestrer via **Kubernetes** pour garantir la haute disponibilité, la scalabilité et faciliter les déploiements dans des environnements cloud ou on-premise.

### Axe 2 : Intelligence Augmentée et Apprentissage Continu

* **Agent avec Mémoire à Long Terme :** Implémenter une base de données vectorielle (ex: ChromaDB, Pinecone) pour permettre à l'agent de se souvenir des incidents passés et de l'efficacité des actions entreprises. Cela ouvrirait la voie à un apprentissage par renforcement basé sur le feedback humain (ex: "cette recommandation était-elle utile ?"). L'agent pourrait ainsi apprendre à prioriser les solutions qui ont fonctionné dans des contextes similaires par le passé.

### Axe 3 : Vers l'Automatisation et le "Self-Healing"

* **Capacités d'Action (Tool-Using étendu) :** Enrichir l'agent avec un set d'outils lui permettant d'**agir** (après validation humaine dans un premier temps) : `restart_service(service_name)`, `scale_cloud_ressource(ressource_id, new_size)`, `run_diagnostic_script(script_name)`.
* **Workflow de Validation :** Mettre en place un système de validation où un ingénieur peut approuver ou rejeter les actions proposées par l'agent, créant une boucle de feedback vertueuse. L'objectif final est de passer d'un système qui **recommande** à un système qui, sur des scénarios maîtrisés et après avoir gagné la confiance des équipes, **résout** de manière autonome les incidents de routine.

# Images de l'interface utilisateur
<img width="1905" height="970" alt="image" src="https://github.com/user-attachments/assets/998471a6-2147-4782-9694-d63071df220f" />
<img width="1901" height="976" alt="image" src="https://github.com/user-attachments/assets/f64a7c4a-9560-40d4-aca6-0cdd6baf23a8" />
<img width="1907" height="974" alt="image" src="https://github.com/user-attachments/assets/af105ba8-daf0-4b2a-9ac0-91f29afabbd6" />
<img width="1904" height="974" alt="image" src="https://github.com/user-attachments/assets/d81f2966-a355-43c7-8860-fd94a46b0a26" />
<img width="1904" height="974" alt="image" src="https://github.com/user-attachments/assets/7a902c27-3c75-4b55-bc99-6402be4fcb20" />
<img width="1909" height="967" alt="image" src="https://github.com/user-attachments/assets/19b41451-2ef6-4733-b64e-10cb1d264efc" />







