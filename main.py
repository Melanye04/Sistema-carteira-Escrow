import uuid
import logging
from datetime import datetime
from decimal import Decimal
from typing import List
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import create_engine, Column, String, Numeric, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Configuração de Logs Físicos
logging.basicConfig(
    filename='transactions.log', 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


SQLALCHEMY_DATABASE_URL = "sqlite:///./escrow.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class EscrowWallet(Base):
    __tablename__ = "escrow_wallet"
    id = Column(String, primary_key=True, default="main_vault")
    balance = Column(Numeric(10, 2), default=0.0)

class EscrowLog(Base):
    __tablename__ = "escrow_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String, index=True)
    amount = Column(Numeric(10, 2))
    status = Column(String, default="HELD") # HELD, RELEASED
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Segurança (API Key)
API_KEY_NAME = "access_token"
API_KEY = "Espanha123"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == API_KEY:
        return api_key
    raise HTTPException(status_code=403, detail="Chave de API inválida")


# Inicialização do App
app = FastAPI(title="Sistema de Escrow Seguro")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/escrow/hold", tags=["Operações"])
def hold_funds(order_id: str, amount: float, db: Session = Depends(get_db), _=Depends(get_api_key)):
    """Retém o valor no sistema de custódia."""
    val = Decimal(str(amount))
    try:
       
        new_log = EscrowLog(order_id=order_id, amount=val)
        db.add(new_log)
        
       
        wallet = db.query(EscrowWallet).filter(EscrowWallet.id == "main_vault").first()
        if not wallet:
            wallet = EscrowWallet(id="main_vault", balance=0)
            db.add(wallet)
        
        wallet.balance += val # type: ignore
        db.commit()
        
        logging.info(f"HOLD: Order {order_id} - R$ {val}")
        return {"status": "success", "retained_amount": val}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/escrow/release/{order_id}", tags=["Operações"])
def release_funds(order_id: str, db: Session = Depends(get_db), _=Depends(get_api_key)):
    """Libera o valor retido."""
    log = db.query(EscrowLog).filter(EscrowLog.order_id == order_id, EscrowLog.status == "HELD").first()
    if not log:
        raise HTTPException(status_code=404, detail="Transação não encontrada ou já liberada")

    wallet = db.query(EscrowWallet).first()
    try:
        wallet.balance -= log.amount # type: ignore
        log.status = "RELEASED" # type: ignore
        db.commit()
        
        logging.info(f"RELEASE: Order {order_id} - R$ {log.amount}")
        return {"status": "released", "order": order_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao liberar fundos")

@app.get("/escrow/balance", tags=["Consulta"])
def get_balance(db: Session = Depends(get_db)):
    wallet = db.query(EscrowWallet).first()
    return {"retained_balance": wallet.balance if wallet else 0}

@app.get("/escrow/list-held", tags=["Consultas"])
def list_held_transactions(db: Session = Depends(get_db), _= Depends(get_api_key)):
    """Lista todas as transações que ainda estão retidas """

    held_transactions = db.query(EscrowLog).filter(EscrowLog.status == "Held").all()

    if not held_transactions:
        return{"message": "Nenhuma transação retida no momento.", "count": 0, "transactions":[]}
    
    return {
        "count": len(held_transactions),
        "transactions": held_transactions
    }

