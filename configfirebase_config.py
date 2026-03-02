"""
Firebase configuration and initialization module.
Uses Firebase Firestore for real-time state management and risk metrics storage.
"""
import os
import logging
from typing import Optional
from dataclasses import dataclass
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import Client as FirestoreClient
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

@dataclass
class FirebaseConfig:
    """Firebase configuration dataclass"""
    project_id: str
    service_account_path: str = "config/service_account.json"
    risk_collection: str = "risk_metrics"
    portfolio_collection: str = "portfolio_states"
    alert_collection: str = "risk_alerts"
    
class FirebaseManager:
    """Singleton Firebase manager with connection pooling and error handling"""
    
    _instance: Optional['FirebaseManager'] = None
    _db: Optional[FirestoreClient] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[FirebaseConfig] = None):
        if not self._initialized:
            self.config = config or FirebaseConfig(
                project_id=os.getenv('FIREBASE_PROJECT_ID', 'risk-trading-engine')
            )
            self._initialize_firebase()
            self._initialized = True
    
    def _initialize_firebase(self) -> None:
        """Initialize Firebase with robust error handling"""
        try:
            # Check for service account file
            if not os.path.exists(self.config.service_account_path):
                logger.error(f"Service account file not found: {self.config.service_account_path}")
                # Try environment variable
                service_account_info = os.getenv('FIREBASE_SERVICE_ACCOUNT')
                if service_account_info:
                    import json
                    cred_info = json.loads(service_account_info)
                    cred = credentials.Certificate(cred_info)
                else:
                    raise FileNotFoundError(
                        f"Firebase service account not found at {self.config.service_account_path}"
                    )
            else:
                cred = credentials.Certificate(self.config.service_account_path)
            
            # Initialize app if not already initialized
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred, {
                    'projectId': self.config.project_id
                })
            
            self._db = firestore.client()
            logger.info("Firebase Firestore initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self._db = None
            raise
    
    @property
    def db(self) -> FirestoreClient:
        """Get Firestore client with lazy initialization"""
        if self._db is None:
            self._initialize_firebase()
            if self._db is None:
                raise ConnectionError("Firebase connection failed")
        return self._db
    
    def write_risk_metric(self, metric_data: dict, symbol: str) -> str:
        """Write risk metric to Firestore with timestamp"""
        try:
            if self._db is None:
                raise ConnectionError("Firebase not initialized")
            
            # Add timestamp
            metric_data['timestamp'] = firestore.SERVER_TIMESTAMP
            metric_data['symbol'] = symbol
            
            # Write to collection
            doc_ref = self._db.collection(self.config.risk_collection).document()
            doc_ref.set(metric_data)
            logger.debug(f"Risk metric written for {symbol}: {metric_data.get('risk_score', 'N/A')}")
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Failed to write risk metric: {e}")
            # Fallback to local logging
            logger.info(f"Local fallback - Risk metric for {symbol}: {metric_data}")
            return "local_fallback"
    
    def get_portfolio_state(self, portfolio_id: str) -> dict:
        """Retrieve current portfolio state from Firestore"""
        try:
            if self._db is None:
                return {}
            
            doc = self._db.collection(self.config.portfolio_collection).document(portfolio_id).get()
            return doc.to_dict() if doc.exists else {}
            
        except Exception as e:
            logger.error(f"Failed to get portfolio state: {e}")
            return {}
    
    def create_risk_alert(self, alert_data: dict) -> None:
        """Create a risk alert with severity classification"""
        try:
            if self._db is None:
                logger.warning(f"Risk alert (local): {alert_data}")
                return
            
            alert_data['timestamp'] = firestore.SERVER_TIMESTAMP
            alert_data['acknowledged'] = False
            
            self._db.collection(self.config.alert_collection).add(alert_data)
            logger.warning(f"Risk alert created: {alert_data.get('message')}")
            
        except Exception as e:
            logger.error(f"Failed to create risk alert: {e}")