import datetime
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "tarefas_db"),
        user=os.getenv("DB_USER", "tarefas_user"),
        password=os.getenv("DB_PASSWORD", "tarefas_pass"),
    )


def init_db(tentativas: int = 30, espera: int = 2):
    """Cria a tabela. Tenta várias vezes porque o Postgres pode demorar a ficar pronto."""
    for i in range(1, tentativas + 1):
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tarefas (
                        id SERIAL PRIMARY KEY,
                        titulo VARCHAR(255) NOT NULL,
                        descricao TEXT,
                        prioridade VARCHAR(10) NOT NULL DEFAULT 'MEDIA',
                        criado_em TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
            print("Banco de dados pronto.")
            return
        except psycopg2.OperationalError as e:
            print(f"Aguardando banco ({i}/{tentativas}): {e}")
            time.sleep(espera)
    raise RuntimeError("Não foi possível conectar ao banco de dados.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="API de Gerenciamento de Tarefas",
    description="API RESTful conteinerizada em Docker e documentada com OpenAPI 3.0 / Swagger UI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


class TarefaDTO(BaseModel):
    titulo: str = Field(..., example="Configurar Docker", description="Título resumido da tarefa")
    descricao: Optional[str] = Field(None, example="Subir contêineres da API e do Banco de Dados", description="Detalhamento opcional")
    prioridade: Optional[str] = Field("MEDIA", example="ALTA", description="Nível de urgência: BAIXA, MEDIA ou ALTA")


class TarefaResponse(BaseModel):
    id: int = Field(..., example=1)
    titulo: str = Field(..., example="Configurar Docker")
    descricao: Optional[str] = Field(None, example="Subir contêineres da API e do Banco de Dados")
    prioridade: Optional[str] = Field("MEDIA", example="ALTA")
    criado_em: str = Field(..., example="2026-11-09T18:00:00")


def linha_para_dict(row: dict) -> dict:
    row["criado_em"] = row["criado_em"].isoformat()
    return row


@app.get(
    "/api/v1/tarefas",
    response_model=List[TarefaResponse],
    summary="Listar todas as tarefas",
    tags=["Tarefas"],
)
def listar_tarefas():
    """Retorna a listagem cronológica de tarefas cadastradas."""
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, titulo, descricao, prioridade, criado_em FROM tarefas ORDER BY id"
        )
        return [linha_para_dict(r) for r in cur.fetchall()]


@app.post(
    "/api/v1/tarefas",
    response_model=TarefaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar nova tarefa",
    tags=["Tarefas"],
)
def criar_tarefa(tarefa: TarefaDTO):
    """Cadastra uma nova tarefa na base com validação estrita."""
    if not tarefa.titulo.strip():
        raise HTTPException(status_code=400, detail="Título é obrigatório.")

    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO tarefas (titulo, descricao, prioridade, criado_em)
            VALUES (%s, %s, %s, %s)
            RETURNING id, titulo, descricao, prioridade, criado_em
            """,
            (
                tarefa.titulo.strip(),
                tarefa.descricao,
                tarefa.prioridade or "MEDIA",
                datetime.datetime.now(),
            ),
        )
        return linha_para_dict(cur.fetchone())
