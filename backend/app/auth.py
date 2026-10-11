import os, datetime, bcrypt, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SEGREDO = os.getenv("JWT_SECRET", "troque-em-producao")
bearer = HTTPBearer()

def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()

def confere_pin(pin: str, h: str) -> bool:
    return bcrypt.checkpw(pin.encode(), h.encode())

def gera_token(matricula: str, nome: str, funcao: str) -> str:
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)  # um turno
    return jwt.encode({"sub": matricula, "nome": nome, "funcao": funcao, "exp": exp}, SEGREDO, algorithm="HS256")

def exige(funcao: str):
    def checa(cred: HTTPAuthorizationCredentials = Depends(bearer)):
        try:
            dados = jwt.decode(cred.credentials, SEGREDO, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(401, "Crachá inválido ou expirado")
        if dados["funcao"] not in (funcao, "gerente"):
            raise HTTPException(403, "Sem permissão para esta área")
        return dados
    return checa
